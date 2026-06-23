# 04 — LangGraph Agentic Workflows (Tools, Planning, Self-Healing)

> **Goal:** Build agents that *reason, call tools, plan multi-step work, and recover
> from failure* using LangGraph. We go from a basic tool-using ReAct loop to a planner +
> executor with self-healing, human-in-the-loop, and durable state.

---

## 1. Why a graph, not a `while` loop?

A naive agent is `while not done: think(); act()`. That works until you need:
**branching** (route by intent), **retries with repair**, **parallel tool calls**,
**human approval**, **persistence** (resume after crash), and **observability**.

LangGraph models the agent as a **state machine**: nodes (functions) read/write a shared
**state**, edges decide what runs next. This makes control flow *explicit, inspectable,
durable, and testable* — the difference between a demo and a system you can operate.

```
        ┌──────────────────── STATE (messages, plan, scratchpad, step) ───────────────────┐
        │                                                                                  │
   ┌────▼────┐   route   ┌──────────┐  tool_calls?  ┌───────────┐  results  ┌──────────┐  │
──►│ planner │──────────►│ reasoner │──────────────►│  tools    │──────────►│ reasoner │──┘
   └─────────┘           └────┬─────┘      no         └───────────┘            (loop)
                              │ done                      │ error
                              ▼                            ▼
                          ┌────────┐                ┌─────────────┐
                          │ finish │                │ self-heal   │ (retry/repair/replan)
                          └────────┘                └─────────────┘
```

---

## 2. State: the single source of truth

State is a typed dict; LangGraph merges each node's returned partial update. Use
**reducers** (like `add_messages`) for fields that accumulate.

```python
from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # conversation + tool calls/results (appends)
    plan: list[str]                           # remaining steps
    scratchpad: dict                          # intermediate findings
    retries: int                              # for self-healing budget
```

---

## 3. Tools: the agent's hands

Tools are typed functions the model can call. **Clear names, docstrings, and typed args
matter** — that text is the model's only spec for when/how to use them. Treat tool
design like API design.

```python
from langchain_core.tools import tool

@tool
def search_knowledge_base(query: str, doc_type: str | None = None) -> str:
    """Search the enterprise knowledge base. Use for policy, product, or process
    questions. `doc_type` optionally filters (e.g. 'policy', 'contract')."""
    return rag_answer(query, filters={"doc_type": doc_type})["answer"]   # from T01

@tool
def lookup_customer(customer_id: str) -> dict:
    """Fetch a customer record from the CRM by id. Use when the user references a
    specific account, order, or ticket."""
    return crm_client.get(customer_id)                                    # from T08

TOOLS = [search_knowledge_base, lookup_customer]
```

Tool design rules:
- **One clear job per tool.** Don't make a god-tool with a `mode` flag.
- **Return structured, compact results.** The model pays tokens for everything you return.
- **Validate inputs** (Pydantic) and **never trust args blindly** — a tool that runs SQL
  or shell is an injection surface (see [T09](09-security-governance.md)).
- **Make tools idempotent** where possible; the agent may retry them.

---

## 4. The reasoning node (tool-calling loop)

Bind tools to the model; it decides whether to call one or answer.

```python
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import ToolNode

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0).bind_tools(TOOLS)

def reasoner(state: AgentState) -> dict:
    return {"messages": [llm.invoke(state["messages"])]}

def route_after_reasoner(state: AgentState) -> Literal["tools", "finish"]:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "finish"

graph = StateGraph(AgentState)
graph.add_node("reasoner", reasoner)
graph.add_node("tools", ToolNode(TOOLS))     # executes tool_calls, appends results
graph.add_edge(START, "reasoner")
graph.add_conditional_edges("reasoner", route_after_reasoner, {"tools": "tools", "finish": END})
graph.add_edge("tools", "reasoner")          # results feed back → reason again
agent = graph.compile()
```

> **Prefer the prebuilt when it fits.** `langgraph.prebuilt.create_react_agent(llm,
> TOOLS)` gives you this exact loop in one line. Build the graph by hand when you need
> custom planning, routing, or self-healing — covered next.

---

## 5. Planning: decompose before acting

For multi-step tasks, a **plan-and-execute** structure beats a pure ReAct loop: a planner
writes explicit steps, an executor runs them, and a replanner adapts when reality
diverges. This reduces flailing and makes the agent's intent auditable.

```python
PLANNER = """You are a planning agent. Break the user's request into an ordered list of
concrete steps, each achievable with the available tools. Return a JSON list of strings.

Tools: search_knowledge_base, lookup_customer
Request: {request}"""

def planner(state: AgentState) -> dict:
    import json
    raw = llm.invoke(PLANNER.format(request=state["messages"][-1].content)).content
    return {"plan": json.loads(raw)}

def replan(state: AgentState) -> dict:
    """After each step, decide if the remaining plan still makes sense."""
    remaining = state["plan"][1:]
    # ask the model whether to keep, edit, or finish given scratchpad findings
    ...
    return {"plan": remaining}
```

When to use which:

| Pattern | Best for |
|---------|----------|
| **ReAct (reason+act loop)** | open-ended Q&A, few steps, tool choice obvious |
| **Plan-and-execute** | multi-step tasks, need auditability, expensive steps |
| **Router/supervisor + sub-agents** | distinct skills (SQL agent, doc agent, CRM agent) |

---

## 6. Self-healing: recover instead of crashing

Real tools fail: timeouts, rate limits, malformed args, empty results. A production agent
**detects failure, diagnoses, and repairs** within a bounded budget.

### 6.1 Wrap tools so failures become signals, not exceptions

```python
@tool
def run_sql(query: str) -> dict:
    """Run a read-only SQL query against the analytics DB."""
    try:
        return {"ok": True, "rows": db.execute(query)}
    except Exception as e:
        # return the error TO THE MODEL so it can fix its own query
        return {"ok": False, "error": str(e), "hint": "Check column names and quoting."}
```

### 6.2 A self-healing node with a retry budget

```python
def self_heal(state: AgentState) -> dict:
    if state["retries"] >= 3:                              # bounded — never loop forever
        return {"messages": [("assistant",
                "I couldn't complete this after several attempts. Escalating to a human.")]}
    # feed the error back and let the model produce a corrected tool call
    repair = llm.invoke(state["messages"] + [
        ("user", "The last tool call failed. Diagnose the cause and try a corrected approach.")
    ])
    return {"messages": [repair], "retries": state["retries"] + 1}

def route_after_tools(state) -> Literal["reasoner", "self_heal"]:
    last = state["messages"][-1].content
    return "self_heal" if '"ok": false' in str(last).lower() else "reasoner"
```

Self-healing principles:
- **Bound everything.** Retry budget, step budget, total token/time budget. Runaway
  agents are a cost and safety incident.
- **Feed errors back to the model.** LLMs are good at fixing their own malformed calls
  when shown the error — this is the core self-heal mechanism.
- **Escalate gracefully.** When the budget is exhausted, hand off to a human or return a
  clear "I can't" — never a silent wrong answer.
- **Validate tool args before executing** (Pydantic) so you catch errors early and cheaply.

---

## 7. Durability, memory & human-in-the-loop

### 7.1 Checkpointing — resume after a crash

A **checkpointer** persists state after every node, so a long workflow survives a restart
and a chat remembers prior turns. Use Postgres/Redis in production.

```python
from langgraph.checkpoint.postgres import PostgresSaver
checkpointer = PostgresSaver.from_conn_string(POSTGRES_URL)
agent = graph.compile(checkpointer=checkpointer)

# thread_id scopes the persistent state to one conversation/session
config = {"configurable": {"thread_id": "user-123-session-7"}}
agent.invoke({"messages": [("user", "Summarize Acme's open tickets")]}, config)
```

### 7.2 Human-in-the-loop — pause for approval on risky actions

Interrupt before a tool that sends email, issues refunds, or writes to prod:

```python
from langgraph.types import interrupt, Command

def approval_gate(state: AgentState):
    decision = interrupt({"action": "send_email", "to": state["scratchpad"]["recipient"]})
    if decision != "approve":
        return {"messages": [("assistant", "Action cancelled by reviewer.")]}
    return {}   # proceed
# resume later with: agent.invoke(Command(resume="approve"), config)
```

### 7.3 Short- vs long-term memory

- **Short-term:** the `messages` thread, scoped by `thread_id` (above).
- **Long-term:** a `Store` for facts that persist across sessions (user preferences,
  prior resolutions). Retrieve relevant memories into context at the start of a turn —
  this is itself a small RAG over the user's history.

---

## 8. Multi-agent / supervisor pattern

When skills are distinct, a **supervisor** routes to specialist sub-agents. Each
sub-agent is its own compiled graph with its own tools — easier to test and reason about
than one mega-agent.

```python
def supervisor(state) -> Literal["doc_agent", "crm_agent", "sql_agent", "finish"]:
    """Classify the request and route to the right specialist."""
    intent = classify(state["messages"][-1].content)        # cheap classifier (Haiku)
    return {"docs": "doc_agent", "account": "crm_agent",
            "data": "sql_agent"}.get(intent, "finish")
```

Keep the **supervisor cheap and deterministic** where you can (a classifier, not a full
reasoning loop) — it runs on every request.

---

## 9. Observability & cost control

Agents make many LLM + tool calls; you must see inside them.

- **Tracing:** LangSmith / OpenTelemetry — capture every node, prompt, tool call, latency,
  and token count. Without traces, debugging an agent is guessing.
- **Budgets:** enforce max steps, max tokens, max wall-clock per request.
- **Model tiering:** route easy steps (classification, query rewrite) to **Haiku**, hard
  reasoning to **Sonnet/Opus**. Most cost savings come from *not* using a frontier model
  for trivial steps.
- **Streaming:** stream tokens and intermediate steps to the UI so long agent runs feel
  responsive (see [T07](07-fastapi-microservices.md)).

---

## 10. Checklist & pitfalls

- [ ] Model the agent as an explicit graph; keep state typed with reducers.
- [ ] Design tools like APIs: one job, typed args, compact structured returns, validated inputs.
- [ ] Choose the pattern to the task: ReAct (simple), plan-execute (multi-step), supervisor (multi-skill).
- [ ] Self-heal with bounded retries; feed tool errors back to the model; escalate when exhausted.
- [ ] Checkpoint state (Postgres/Redis) for durability + chat memory.
- [ ] Human-in-the-loop on irreversible/sensitive actions.
- [ ] Trace everything; tier models by step difficulty; enforce budgets.

| Pitfall | Fix |
|---------|-----|
| Infinite tool loop | step + retry + token budgets, recursion limit |
| Agent ignores a tool | improve tool name/docstring; fewer, clearer tools |
| Wrong tool chosen | better routing/classifier; reduce overlapping tools |
| Silent wrong answer on failure | self-heal + graceful escalation, never fabricate |
| Can't debug behavior | add tracing before adding features |
| Tool-arg injection | validate args, sandbox side effects, least-privilege creds (T09) |

**Next:** [05 — Knowledge Layers & Ontology](05-knowledge-layers.md) — giving agents a
structured, multi-tenant view of enterprise data instead of a flat blob of chunks.
