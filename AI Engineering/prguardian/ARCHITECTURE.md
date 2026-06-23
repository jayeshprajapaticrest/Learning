# PR Guardian — Architecture & Design Notes

For a reader evaluating the system (architect / staff+ reviewer): how the parts
fit, and the reasoning behind each choice.

## 1. Layered view

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Entry            cli.py · examples/*.py · eval/run_eval.py                  │
├──────────────────────────────────────────────────────────────────────────┤
│ Orchestration    graph.py  (LangGraph StateGraph)                          │
│                  └ intake→retrieve→[reviewers]→verify→risk→gate→act→learn→report
├──────────────────────────────────────────────────────────────────────────┤
│ Agents           reviewers.py (fan-out)  ·  single_agent.py (ReAct)         │
│ Reasoning aids   verify.py (reflection)  ·  risk.py (deterministic policy)  │
├──────────────────────────────────────────────────────────────────────────┤
│ Capabilities     tools.py  → standards_search (RAG)                         │
│                            → MCP tools → mcp_server/github_ci_server.py     │
│ Knowledge        ingest.py / retriever.py → Chroma (standards + incidents)  │
├──────────────────────────────────────────────────────────────────────────┤
│ State            memory.py  (SqliteSaver checkpointer + feedback store)     │
│ Contracts        schemas.py (Pydantic)   Observability  observability.py    │
│ Models / config  llm.py → langchain-anthropic → Claude    config.py         │
└──────────────────────────────────────────────────────────────────────────┘
```

## 2. Control flow & concurrency

LangGraph executes in **supersteps**. After `retrieve`, all four reviewer nodes
are scheduled in the same superstep → they run **in parallel**. Their outputs
are merged into `state["findings"]` by an `operator.add` reducer (each reviewer
returns only `{"findings": [...]}`, so there are no write conflicts). `verify`
has an inbound edge from every reviewer, so LangGraph runs it once, **after all
reviewers finish** (fan-in barrier).

```
intake → retrieve ─┬─▶ review_security ──┐
                   ├─▶ review_performance ┤  (parallel)
                   ├─▶ review_correctness ┤
                   └─▶ review_style ──────┴─▶ verify → risk → human_gate → act → learn → report
```

## 3. RAG, two ways

| Collection | Purpose | How it's used |
|---|---|---|
| `standards` | Ground reviewers in the team's rules | each reviewer retrieves lens-specific rules and treats them as ground truth |
| `incidents` | "have we been burned by this before?" | `retrieve` does similarity search on the diff; close matches become a warning in the report |

`ingest.py` is the only writer; `retriever.py` is the only reader. Swap Chroma
for pgvector/Pinecone by editing just those two files.

## 4. Trust mechanisms (the enterprise core)

| Mechanism | File | Why it matters |
|---|---|---|
| Typed structured output | schemas.py | LLM outputs are validated, not regex-parsed |
| Reflection / verification | verify.py | a skeptic drops weak findings → low false-positive rate |
| Deterministic risk policy | risk.py | merge-gating decision is reproducible & auditable |
| Human-in-the-loop gate | graph.py (`interrupt`) | no merge-affecting action without sign-off |
| Self-improving feedback | memory.py | converges on what the team actually values |
| Observability | observability.py | every run is traceable (LangSmith) and logged |
| Evaluation | eval/run_eval.py | prompt/model changes are regression-tested |

**Decision vs. explanation split:** `risk.decide()` computes the decision by a
fixed formula (severity weights × verifier confidence, thresholds in config).
The LLM only writes the human-readable summary and release note. This keeps the
part that gates a merge deterministic while still getting good prose.

## 5. Memory model

| Layer | Backed by | Scope | Powers |
|---|---|---|---|
| Short-term | `SqliteSaver` | one `thread_id` | resumable runs; the HITL interrupt/resume |
| Long-term | feedback store | `(lens, finding)` | the self-improving loop |

The checkpointer is what makes `interrupt` work: at the gate the full graph
state is persisted, so the run can resume — even days later, even after a
restart — with `Command(resume=...)`.

## 6. Model strategy

- **Reviewers (parallel):** `claude-sonnet-4-6` — fast, cheap, four at once.
- **Verifier / risk rationale / report:** `claude-opus-4-8` — the judgements
  that must be right.
- Sampling params / `budget_tokens` are unset (they error on Opus 4.8 / Sonnet
  4.6). Extended thinking, if wanted, is `thinking={"type": "adaptive"}`.

## 7. From demo to production (what changes, what doesn't)

| Concern | Demo | Production — change only this |
|---|---|---|
| GitHub / CI | simulated MCP server | point MCP client at the real GitHub/CI MCP server (tools.py) |
| Vector DB | local Chroma | pgvector / managed vector DB (ingest.py + retriever.py) |
| Long-term memory | in-process store | `PostgresStore` (memory.py) |
| Checkpointer | SQLite | `PostgresSaver` (memory.py) |
| Trigger | CLI / example | a GitHub webhook → `build_graph().ainvoke(...)` |
| Approvals | terminal prompt | Slack/GitHub approval → `Command(resume=...)` |

The **agent code is unchanged** across all of these — that's the payoff of the
LangGraph + MCP + typed-contract structure.

## 8. Extension points

- **New reviewer lens:** add to `LENSES` in reviewers.py; graph.py picks it up
  automatically (it iterates `LENSES`).
- **New action:** add a tool to the MCP server; call it from the `act` node.
- **Stricter gate:** tune thresholds in config.py, or require approval for more
  decision types in risk.py.
- **Streaming UI:** every graph supports `.astream()`.
