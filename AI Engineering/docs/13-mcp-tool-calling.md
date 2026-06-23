# 13 — MCP Tools & Tool-Calling Workflows

> Builds on [T08 §6](08-enterprise-integration.md). Two related topics: **tool-calling
> workflows** (how an LLM reliably uses functions) and **MCP** (the open standard that
> makes tools reusable across models and apps). Master tool-calling first — MCP is a
> transport for the same idea.

---

## Part A — Tool-Calling Workflows

### 1. How tool calling actually works

Modern LLMs are trained to emit **structured tool calls**. The loop:

```
 1. You send: messages + tool schemas (name, description, JSON arg schema)
 2. Model decides: answer directly  OR  emit tool_call(name, args)
 3. Your code runs the tool, appends the result as a tool message
 4. Send back → model uses the result to answer or call another tool
 5. Repeat until the model answers with no tool call
```

The model never executes anything — **it requests, your code runs.** That boundary is
where all safety lives (validation, auth, sandboxing).

### 2. Defining tools the model can use well

The model's *only* knowledge of a tool is its **name, description, and arg schema**. Treat
them like API docs for a junior dev.

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class RefundArgs(BaseModel):
    order_id: str = Field(description="The order ID, format ORD-XXXXX")
    amount: float = Field(gt=0, description="Refund amount in USD, must be > 0")
    reason: str = Field(description="Customer-stated reason")

@tool(args_schema=RefundArgs)
def issue_refund(order_id: str, amount: float, reason: str) -> dict:
    """Issue a refund for an order. Only for orders within the 30-day window.
    Returns {ok, refund_id} or {ok: false, error}."""
    ...
```

Design rules that drive reliability:
- **One clear job per tool**; avoid a god-tool with a `mode` switch.
- **Describe *when* to use it**, not just what it does ("Use for orders within 30 days").
- **Typed, constrained args** (Pydantic validators) — the schema prevents bad calls before
  they run.
- **Return compact, structured results**; include an `ok`/`error` field for self-healing.
- **Keep the toolset small** (≈5–15). Too many overlapping tools confuses selection.

### 3. The raw tool-calling loop (provider SDK)

```python
import anthropic
client = anthropic.Anthropic()
messages = [{"role": "user", "content": "Refund order ORD-12345 for $40, item arrived broken"}]

while True:
    resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=1024,
                                  tools=TOOL_SCHEMAS, messages=messages)
    messages.append({"role": "assistant", "content": resp.content})
    tool_uses = [b for b in resp.content if b.type == "tool_use"]
    if not tool_uses:
        break                                            # model gave a final answer
    results = []
    for tu in tool_uses:
        out = dispatch(tu.name, tu.input)                # validate → run → structured result
        results.append({"type": "tool_result", "tool_use_id": tu.id,
                        "content": json.dumps(out)})
    messages.append({"role": "user", "content": results})
```

In practice you'd use `create_react_agent` ([T11 §4](11-langgraph-features.md)) which is
this loop plus durability/streaming/HITL — but knowing the raw loop is essential for
debugging.

### 4. Parallel & sequential tool use

- **Parallel:** models can request several independent tool calls in one turn — run them
  concurrently (`asyncio.gather`) and return all results. Big latency win.
- **Sequential/dependent:** when tool B needs tool A's output, the model calls A, sees the
  result, then calls B — that's the loop iterating. Don't force parallelism on dependent calls.
- **Forcing behavior:** `tool_choice` can force a specific tool, force *some* tool, or
  allow auto — useful for structured extraction or guaranteeing a step.

### 5. Reliability & safety in tool-calling

- **Validate args** against the schema *before* executing (reject, don't guess).
- **Least privilege** — give each agent only the tools/credentials it needs ([T09](09-security-governance.md)).
- **Idempotency** — retries shouldn't double-charge; use idempotency keys on mutations.
- **Human approval** on irreversible/sensitive actions (refunds, emails, deletes) via
  `interrupt()` ([T11 §8](11-langgraph-features.md)).
- **Errors as feedback** — return the error to the model so it can self-correct (T04 §6);
  bound retries so it can't loop forever.
- **Treat tool *outputs* as untrusted** — they can carry indirect prompt injection ([T06 §2](06-guardrails-evals.md)).
- **Timeouts + budgets** — cap tool latency and total tool calls per request.

---

## Part B — Model Context Protocol (MCP)

### 6. What MCP is and why it exists

Without MCP, every (model × app × data source) integration is bespoke — an N×M explosion.
**MCP** is an open standard (introduced by Anthropic, now broadly adopted) that defines a
uniform client–server protocol. Build an **MCP server** for a data source/tool **once**,
and any MCP-capable **client** (Claude apps, IDEs, your LangGraph agent) can use it.

```
            N clients                         M servers
  ┌──────────┐                       ┌──────────────────┐
  │ Claude   │──┐                 ┌──►│ SharePoint server│
  │ IDE      │──┼── MCP (uniform)─┼──►│ CRM server       │
  │ your agent──┘                 └──►│ Postgres server  │
  └──────────┘   one protocol         └──────────────────┘
  Build a server once → every client gets it. (Solves the N×M integration problem.)
```

### 7. The three MCP primitives

| Primitive | What it is | Controlled by |
|-----------|-----------|---------------|
| **Tools** | callable functions (actions/queries) the model invokes | model (with app/user mediation) |
| **Resources** | readable data (files, records, rows) loaded as context | application/user |
| **Prompts** | reusable, parameterized prompt templates the server offers | user (e.g. slash commands) |

Transports: **stdio** (local subprocess) and **streamable HTTP** (networked/remote).

### 8. Build an MCP server

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("enterprise-kb")

@mcp.tool()
def search_kb(query: str, tenant_id: str) -> str:
    """Search the enterprise knowledge base for policies and docs."""
    return rag_answer(query, filters={"tenant_id": tenant_id})["answer"]

@mcp.resource("contract://{contract_id}")
def contract(contract_id: str) -> str:
    """Return a contract's text as a readable resource."""
    return load_contract_text(contract_id)

@mcp.prompt()
def summarize_contract(contract_id: str) -> str:
    """A reusable prompt template for contract summaries."""
    return f"Summarize the key obligations, dates, and risks in contract {contract_id}."

if __name__ == "__main__":
    mcp.run(transport="stdio")             # or transport="streamable-http" for remote
```

### 9. Consume MCP servers from a LangGraph/LangChain agent

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

client = MultiServerMCPClient({
    "kb":  {"command": "python", "args": ["kb_server.py"], "transport": "stdio"},
    "crm": {"url": "https://crm-mcp.internal/mcp", "transport": "streamable_http"},
})
tools = await client.get_tools()                       # MCP tools → LangChain tools
agent = create_react_agent("anthropic:claude-sonnet-4-6", tools)
# From here, MCP tools behave exactly like native tools in the tool-calling loop (Part A).
```

The adapter converts MCP tools into standard LangChain tools, so everything in Part A
(validation, parallel calls, approval gates, error-as-feedback) applies unchanged.

### 10. MCP security — it's a privileged gateway

An MCP server can read data and take actions, so treat it as a security boundary:
- **Only connect servers you trust**; review their tools before enabling.
- **Scope credentials tightly** — the server should hold least-privilege creds, not
  god-mode tokens ([T09](09-security-governance.md)).
- **Authenticate clients** to remote servers; pass the user's identity so the server can
  enforce tenant/ACL filters.
- **Validate tool inputs** server-side; **gate write tools** behind approval.
- **Audit** every MCP tool call (who, what, args, result) like any other tool.
- Beware **tool-description injection** — a malicious server could embed instructions in a
  tool description; only load trusted servers and consider screening descriptions.

### 11. When to use MCP vs plain tools

| Situation | Choice |
|-----------|--------|
| Tool used only by this one app/agent | plain in-process tool (Part A) |
| Same integration needed by many models/apps/teams | MCP server (reuse) |
| Want Claude Desktop / IDE / other clients to use it | MCP (that's the point) |
| Tight latency, simple function | plain tool (no transport overhead) |
| Centralized auth/audit/governance for a data source | MCP server as the gateway |

**Takeaway:** tool-calling is the mechanism; MCP is a reuse + governance standard layered
on top. Design tools well first; expose them via MCP when reuse or cross-client access
justifies the extra moving part.

**Next:** [14 — Multi-Agent Orchestration](14-multi-agent-orchestration.md).
