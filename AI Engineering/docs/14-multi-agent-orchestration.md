# 14 — Multi-Agent Orchestration

> Builds on [T04](04-langgraph-agents.md) and [T11](11-langgraph-features.md). When does
> one agent become several, and how do you coordinate them? This covers the canonical
> topologies — **supervisor, network, hierarchical, swarm, map-reduce, pipeline** — with
> LangGraph implementations, plus the hard parts: handoffs, shared state, and cost.

---

## 1. When to go multi-agent (and when not to)

A single agent with good tools handles most tasks. Reach for multiple agents when:

- **Distinct skill sets / toolsets** — a SQL analyst, a doc researcher, a code writer each
  need different tools and prompts; one agent with 40 tools chooses poorly.
- **Context isolation** — keeping each agent's context focused improves quality and cost;
  a mega-prompt with everything degrades.
- **Separation of concerns** — easier to test, version, and reason about specialists.
- **Parallelism** — independent subtasks can run concurrently.

**Don't** go multi-agent for: simple linear flows (use a chain), or just to "feel
sophisticated." Every extra agent adds latency, cost, and failure modes. **Start with one
agent; split when a specific pain (tool confusion, context bloat, parallelism) forces it.**

---

## 2. Supervisor (orchestrator–worker)

A central **supervisor** routes each step to a specialist worker and integrates results.
Most common, most controllable topology.

```
            ┌────────────┐
       ┌───►│ supervisor │◄────┐  (workers report back; supervisor decides next)
       │    └─────┬──────┘     │
       │   ┌──────┼──────┐     │
       ▼   ▼      ▼      ▼     ▼
   research  sql   writer  crm  (specialist agents)
```

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from typing import Literal

def supervisor(state) -> Command[Literal["research", "sql", "writer", "__end__"]]:
    decision = router_llm.invoke(state["messages"])     # pick next worker or finish
    nxt = decision["next"]                               # "research" | "sql" | "writer" | "FINISH"
    return Command(goto=END if nxt == "FINISH" else nxt)

def research(state) -> Command[Literal["supervisor"]]:
    result = researcher_agent.invoke(state)             # a create_react_agent subgraph
    return Command(goto="supervisor", update={"messages": result["messages"][-1:]})

g = StateGraph(State)
for n, fn in [("supervisor", supervisor), ("research", research), ("sql", sql_node), ("writer", writer_node)]:
    g.add_node(n, fn)
g.add_edge(START, "supervisor")
app = g.compile()
```

Prebuilt: **`langgraph-supervisor`** wraps this. Keep the supervisor's routing **cheap and
near-deterministic** (a classifier) since it runs every hop.

---

## 3. Network (fully connected)

Every agent can hand off to every other agent — no central router. Flexible but harder to
control and reason about; use when collaboration is genuinely peer-to-peer.

```python
def agent_a(state) -> Command[Literal["agent_b", "agent_c", END]]:
    out = a_llm.invoke(state["messages"])
    return Command(goto=out["handoff_to"], update={"messages": [out["msg"]]})
```

Add **handoff budgets/limits** — networks can ping-pong indefinitely without them.

---

## 4. Hierarchical (teams of teams)

When you have many agents, group them into **teams**, each led by a sub-supervisor, all
under a top supervisor. Implemented with **nested subgraphs** ([T11 §10](11-langgraph-features.md)).

```
                 top supervisor
                 /            \
        research team      ops team
        /     |             |     \
   web   docs            sql    crm
```

Each team is a compiled graph used as a node. This scales agent count while keeping any
single supervisor's decision space small.

---

## 5. Swarm (decentralized handoff)

Agents hand control directly to one another via **handoff tools**; the system "remembers"
which agent is active (in state). No central supervisor.

```python
from langgraph.types import Command
from langchain_core.tools import tool

@tool
def transfer_to_billing() -> Command:
    """Hand the conversation to the billing specialist."""
    return Command(goto="billing", graph=Command.PARENT, update={"active": "billing"})

# each agent has handoff tools to its peers; control follows the handoffs
```

Prebuilt: **`langgraph-swarm`**. Good for customer-support-style flows where the
"specialist on the line" changes as the topic shifts.

---

## 6. Map-reduce (parallel fan-out)

Fan out the same task over many items in parallel, then aggregate — the multi-agent
version of [T11 §3.4](11-langgraph-features.md) `Send`.

```python
from langgraph.types import Send

def fan_out(state):                                   # map: one worker per document
    return [Send("summarize", {"doc": d}) for d in state["docs"]]

def reduce(state):                                    # reduce: combine all summaries
    return {"report": synth_llm.invoke(state["summaries"])}

g.add_conditional_edges("split", fan_out, ["summarize"])
g.add_edge("summarize", "reduce")
# summaries field uses a list-append reducer so parallel workers don't clobber each other
```

Classic uses: summarize 100 docs, evaluate N candidates, run the same analysis across
regions. Wall-clock ≈ slowest single worker, not the sum.

---

## 7. Pipeline / sequential (assembly line)

Agents in a fixed order, each transforming the previous output: `plan → research → draft →
critique → finalize`. Add a **critique/reflection** agent that can loop back to an earlier
stage — a powerful quality pattern.

```python
g.add_edge("draft", "critique")
def critique_route(state) -> Literal["draft", "finalize"]:
    return "draft" if state["critique"]["needs_revision"] else "finalize"
g.add_conditional_edges("critique", critique_route)   # revise until good enough (bounded!)
```

---

## 8. The hard parts (where multi-agent systems break)

### 8.1 Handoffs & control transfer

Use **`Command(goto=..., graph=Command.PARENT)`** to move control between agents that live
in a parent graph. Decide whether a handoff passes the **full message history** or a
**compact summary** — passing everything bloats context and cost; passing too little loses
information. Summarize at boundaries when histories grow.

### 8.2 Shared vs private state

- **Shared state** — agents read/write a common State; simple but agents can interfere.
  Use **reducers** so parallel writes merge ([T11 §1](11-langgraph-features.md)).
- **Private state + explicit messages** — each agent has its own scratchpad; they exchange
  only deliberate messages. More isolation, less interference. Often the better default.

### 8.3 Communication patterns

Agents communicate via the **shared message list** (everyone sees everything) or
**point-to-point** (a supervisor relays). Full visibility helps coordination but costs
tokens and can cause echo/confusion; choose per system.

### 8.4 Termination & loop control

Multi-agent systems can loop forever (A→B→A…). **Always bound**: max handoffs, max total
steps, `recursion_limit`, and a clear FINISH condition the supervisor can reach.

### 8.5 Cost & latency

Every agent step is ≥1 LLM call; multi-agent multiplies them. Controls:
- **Tier models** — cheap model (Haiku) for routing/simple workers, strong (Sonnet/Opus)
  for hard reasoning.
- **Parallelize** independent work (map-reduce) to cut wall-clock.
- **Cap context** passed between agents.
- **Budget per request** — total tokens/time/steps ([T04 §9](04-langgraph-agents.md)).

### 8.6 Observability

Trace **every agent, handoff, and tool call** (LangSmith/OTel). Multi-agent bugs are
emergent — you cannot debug them without seeing the full interaction graph.

---

## 9. Choosing a topology

| Topology | Use when | Control | Cost |
|----------|----------|---------|------|
| **Single agent** | most tasks; clear toolset | highest | lowest |
| **Supervisor** | distinct specialists, want control | high | medium |
| **Hierarchical** | many agents, need structure | high | higher |
| **Network** | peer collaboration, flexible | low | high |
| **Swarm** | topic-shifting handoffs (support) | medium | medium |
| **Map-reduce** | parallel over many items | high | scales w/ items |
| **Pipeline + critique** | quality via iterative refinement | high | medium |

**Default ladder:** single agent → supervisor (when specialists emerge) → hierarchical
(when agent count grows) → network/swarm (only when peer handoff is genuinely needed).

## 10. Checklist

- [ ] Justify each agent — start single, split only on real pain (tool confusion, context bloat, parallelism).
- [ ] Pick a topology deliberately; default to supervisor for control.
- [ ] Define handoff payloads (full history vs summary); summarize at boundaries.
- [ ] Use reducers for shared state; prefer private state + explicit messages when isolation matters.
- [ ] Bound everything: max handoffs, steps, recursion limit, explicit FINISH.
- [ ] Tier models, parallelize independent work, cap inter-agent context, set per-request budgets.
- [ ] Trace every agent/handoff/tool call.

**Next:** [15 — Prompt Engineering & Hallucination Control](15-prompt-engineering-hallucination.md).
