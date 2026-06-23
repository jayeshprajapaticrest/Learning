# 11 — LangGraph: Complete Feature Reference (Single & Multi-Agent)

> Builds on [T04](04-langgraph-agents.md). This is a **feature-by-feature reference** for
> everything LangGraph gives you to build single agents and multi-agent systems: state,
> graphs, nodes/edges, control flow, persistence, memory, streaming, human-in-the-loop,
> subgraphs, and the prebuilt agent. Each feature has a minimal, runnable snippet.

LangGraph models an agent as a **stateful graph**: a shared State object flows through
Nodes (functions) connected by Edges (routing). It adds what a plain loop can't: cycles,
branching, durability, parallelism, interruption, and composition.

---

## 1. State — the typed, reducible data bus

State is a `TypedDict` (or Pydantic model / dataclass). Each node returns a **partial
update**; LangGraph merges it. **Reducers** control how a field merges.

```python
from typing import Annotated, TypedDict
from operator import add
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]   # reducer: append + dedupe by id
    visited:  Annotated[list[str], add]       # reducer: concatenate lists
    plan: list[str]                           # no reducer: last write wins (overwrite)
    counter: int
```

- **Default (no reducer):** new value overwrites.
- **`add_messages`:** appends messages, handles updates by id — the standard for chat.
- **Custom reducer:** any `(old, new) -> merged` function — vital for parallel branches
  that all write the same field (otherwise they clobber each other).
- **Multiple state schemas:** a graph can have separate **input**, **output**, and
  internal state schemas to keep the public contract clean.

---

## 2. Graph construction — nodes, edges, START/END

```python
from langgraph.graph import StateGraph, START, END

g = StateGraph(State)
g.add_node("plan", plan_fn)                 # node = (state) -> partial update
g.add_node("act", act_fn)
g.add_edge(START, "plan")                   # normal (unconditional) edge
g.add_edge("plan", "act")
g.add_edge("act", END)
app = g.compile()
```

- **Node**: a function (or any LangChain Runnable) taking state, returning an update.
- **Normal edge**: always go A→B.
- **START / END**: virtual entry/exit nodes.

---

## 3. Control flow

### 3.1 Conditional edges (branching/routing)

```python
def route(state) -> str:                    # returns the name of the next node
    return "tools" if state["messages"][-1].tool_calls else "done"

g.add_conditional_edges("agent", route, {"tools": "tools", "done": END})
```

### 3.2 Cycles (the reason LangGraph exists)

Edges can loop — `tools → agent → tools …` — enabling the core agent loop. A
**`recursion_limit`** (default 25) prevents infinite loops:

```python
app.invoke(input, {"recursion_limit": 50})
```

### 3.3 `Command` — update state *and* route in one return

A node can both write state and decide where to go next, which is how agents hand off to
each other (key for multi-agent):

```python
from langgraph.types import Command
from typing import Literal

def agent_a(state) -> Command[Literal["agent_b", END]]:
    return Command(goto="agent_b", update={"messages": [result]})
```

### 3.4 `Send` — dynamic fan-out (map-reduce / parallelism)

Spawn N parallel branches at runtime, one per item — the **map** step of map-reduce. The
number of branches need not be known when you build the graph:

```python
from langgraph.types import Send

def fan_out(state):
    return [Send("worker", {"item": x}) for x in state["items"]]   # one worker per item

g.add_conditional_edges("split", fan_out, ["worker"])
# workers run in parallel; results merge via a reducer on the shared field (see §1)
```

### 3.5 Parallel nodes (superstep execution)

If multiple edges leave a node, those targets run **in the same superstep (parallel)**.
Use reducers so their writes to shared fields merge instead of overwrite.

---

## 4. The prebuilt ReAct agent

For the common tool-calling agent, skip hand-wiring:

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[search_kb, lookup_customer],
    prompt="You are a helpful enterprise assistant.",     # system prompt
    checkpointer=checkpointer,                            # optional memory (§6)
)
agent.invoke({"messages": [("user", "Find Acme's open tickets")]})
```

`create_react_agent` builds the agent↔tools loop, supports structured output, dynamic
prompts, pre/post-model hooks, and accepts a checkpointer/store. Reach for a custom graph
only when you need planning, custom routing, or self-healing beyond the loop.

---

## 5. Tools & the ToolNode

```python
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool

@tool
def search_kb(query: str) -> str:
    """Search the knowledge base."""
    return rag_answer(query)["answer"]

g.add_node("tools", ToolNode([search_kb]))          # executes tool_calls, appends ToolMessages
g.add_conditional_edges("agent", tools_condition)   # prebuilt: route to tools if tool_calls present
g.add_edge("tools", "agent")
```

- **`ToolNode`** runs all tool calls in the last message (in parallel) and appends results.
- **`tools_condition`** is the prebuilt router for "tools or end?".
- **Error handling:** `ToolNode(handle_tool_errors=...)` turns tool exceptions into
  messages the model can recover from (self-healing, T04 §6).
- **Tools can read state / write state / trigger interrupts** via `InjectedState` and
  `Command` returns — tools aren't limited to pure functions.

---

## 6. Persistence (checkpointing) — durability + memory

A **checkpointer** snapshots state after every superstep, keyed by `thread_id`. This gives
you crash recovery, conversation memory, time-travel, and human-in-the-loop.

```python
from langgraph.checkpoint.memory import MemorySaver         # dev
from langgraph.checkpoint.postgres import PostgresSaver     # prod (also Redis, SQLite)

app = g.compile(checkpointer=PostgresSaver.from_conn_string(DB_URL))
cfg = {"configurable": {"thread_id": "session-42"}}
app.invoke({"messages": [("user", "hi")]}, cfg)             # turn 1
app.invoke({"messages": [("user", "continue")]}, cfg)       # turn 2 remembers turn 1
```

Checkpointer-powered features:
- **Threads** — each `thread_id` is an isolated, resumable conversation/run.
- **State inspection** — `app.get_state(cfg)` returns current values + next nodes.
- **History / time-travel** — `app.get_state_history(cfg)` lists every checkpoint; resume
  from any past checkpoint to fork an alternate path.
- **Update state manually** — `app.update_state(cfg, {...})` to inject corrections.

---

## 7. Long-term memory — the Store

Checkpointers persist *thread* state. The **Store** persists knowledge **across** threads
(user preferences, learned facts) — namespaced and optionally vector-searchable.

```python
from langgraph.store.memory import InMemoryStore
store = InMemoryStore(index={"embed": embed_fn, "dims": 1024})   # enables semantic recall
app = g.compile(checkpointer=checkpointer, store=store)

# inside a node (store is injected):
def node(state, *, store):
    store.put(("memories", user_id), key="pref", value={"tone": "concise"})
    hits = store.search(("memories", user_id), query="communication style")  # semantic
```

This is how an agent "remembers you" between sessions — effectively RAG over the user's
own history.

---

## 8. Human-in-the-loop

### 8.1 `interrupt()` — pause for input mid-run

```python
from langgraph.types import interrupt, Command

def review(state):
    decision = interrupt({"proposed_action": state["draft"]})   # execution pauses here
    return {"approved": decision == "approve"}

# run pauses; later resume with the human's answer:
app.invoke(Command(resume="approve"), cfg)
```

Requires a checkpointer (state must persist across the pause). Use for **approve/edit/
reject** gates on risky actions, or to ask the user a clarifying question.

### 8.2 `interrupt_before` / `interrupt_after`

Statically pause around specific nodes for review:

```python
app = g.compile(checkpointer=cp, interrupt_before=["execute_payment"])
```

---

## 9. Streaming

LangGraph streams at multiple granularities — essential for responsive UX (T07 §5):

```python
for chunk in app.stream(input, cfg, stream_mode="updates"):   # state deltas per node
    ...
for token, meta in app.stream(input, cfg, stream_mode="messages"):  # LLM tokens
    print(token.content, end="")
# other modes: "values" (full state each step), "debug", "custom" (emit your own events)
```

- **`updates`** — what each node changed (great for "agent is now searching…").
- **`messages`** — token-by-token LLM output.
- **`values`** — full state snapshots.
- **`custom`** — emit progress events from inside a node via `get_stream_writer()`.
- Multiple modes at once: `stream_mode=["updates", "messages"]`.

---

## 10. Subgraphs — composition & encapsulation

A compiled graph can be a **node** in a bigger graph. This is the foundation of
multi-agent systems: each agent is a subgraph; a parent graph orchestrates them.

```python
researcher = build_researcher_graph().compile()    # its own state, tools, loop
writer = build_writer_graph().compile()

parent = StateGraph(ParentState)
parent.add_node("research", researcher)             # subgraph as a node
parent.add_node("write", writer)
parent.add_edge("research", "write")
```

Subgraphs can **share state keys** with the parent (automatic mapping) or use a
**transform** function when schemas differ. Streaming/checkpointing propagate into
subgraphs (`subgraphs=True`).

---

## 11. Multi-agent topologies in LangGraph

LangGraph expresses every common topology (deep dive in [T14](14-multi-agent-orchestration.md)):

| Topology | How LangGraph expresses it |
|----------|----------------------------|
| **Supervisor** | a router node returns `Command(goto=<chosen agent>)`; agents return to supervisor |
| **Network** | agents are nodes; each can `Command(goto=any other)` — fully connected |
| **Hierarchical** | supervisors of supervisors via nested subgraphs |
| **Swarm / handoff** | agents hand control to each other directly via `Command` + handoff tools |
| **Map-reduce** | `Send` to fan out workers, reducer to gather |

Prebuilt helpers exist (`langgraph-supervisor`, `langgraph-swarm`) that wrap these patterns.

```python
# Handoff tool — lets one agent transfer control to another (swarm pattern)
from langgraph.types import Command
@tool
def handoff_to_writer(state) -> Command:
    """Transfer the task to the writer agent."""
    return Command(goto="writer", graph=Command.PARENT)   # jump in the parent graph
```

---

## 12. Configuration, runtime context & durability modes

- **`config`/`RunnableConfig`** — pass per-run values (`thread_id`, `recursion_limit`,
  `tags`, user/runtime context) without putting them in state.
- **Runtime context / `configurable`** — inject dependencies (db handles, user id, model
  choice) read by nodes at runtime.
- **Durability modes** — control how often checkpoints are written (`"exit"`, `"async"`,
  `"sync"`) to trade durability vs latency.
- **Caching** — node-level caching to skip recomputing identical work.
- **Retry policies** — per-node `RetryPolicy` for transient failures.

---

## 13. Deployment & observability

- **LangGraph Platform / Server** — deploy graphs as APIs with built-in persistence, a
  task queue, cron, and a **Studio** for visual debugging/time-travel.
- **Assistants** — versioned configurations of a graph (different prompts/models/tools)
  served from the same deployment.
- **LangSmith tracing** — every node, prompt, tool call, token, and latency captured;
  the practical way to debug agent behavior (T04 §9).

---

## 14. Feature → use-case cheat sheet

| You need… | Use |
|-----------|-----|
| A tool-calling agent fast | `create_react_agent` (§4) |
| Loops / branching control flow | conditional edges + cycles (§3) |
| Update state *and* route | `Command` (§3.3) |
| Parallel work over N items | `Send` + reducer (§3.4) |
| Conversation memory | checkpointer + `thread_id` (§6) |
| Cross-session memory | Store (§7) |
| Approval / clarification mid-run | `interrupt()` (§8) |
| Responsive UI | streaming modes (§9) |
| Compose agents | subgraphs (§10) |
| Coordinate many agents | supervisor/network/swarm via `Command` (§11, T14) |
| Crash recovery / resume | checkpointer + durability modes (§6, §12) |

**Next:** [12 — LangChain Complete Feature Reference](12-langchain-features.md).
