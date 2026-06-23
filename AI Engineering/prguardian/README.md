# PR Guardian — a self-improving, human-gated multi-agent code & release reviewer

> Built with **LangGraph + Claude**. A senior-engineer-grade reference system
> you can demo to your org: it reviews a pull request with a team of specialist
> AI agents, grounds every claim in your engineering standards (RAG), flags
> changes that resemble past incidents, scores risk deterministically, **pauses
> for a human to approve any merge-affecting action**, acts on GitHub/CI via
> MCP, and **learns from the feedback** so it gets quieter and sharper over time.

This goes beyond a chatbot demo. It deliberately includes the things that decide
whether an agentic system is allowed near production in an MNC:

- ✅ Single agent **and** multi-agent orchestration
- ✅ RAG + vector storing/searching (two collections: standards & incidents)
- ✅ MCP tools (GitHub + CI), discovered at runtime
- ✅ Short-term **and** long-term memory
- ✅ **Reflection / verification loop** (kills false positives)
- ✅ **Human-in-the-loop approval gates** (LangGraph `interrupt`)
- ✅ **Deterministic, auditable risk scoring** (LLM explains, code decides)
- ✅ **Self-improving memory** (learns which findings the team accepts)
- ✅ **Observability** (LangSmith hook + local run log)
- ✅ **Evaluation harness** (measure before you trust)

---

## Component → file map

| Topic | Where it lives | One-liner |
|---|---|---|
| **Multi-agent orchestration** | [graph.py](prguardian/src/prguardian/graph.py) | the LangGraph pipeline that runs the whole review |
| **Specialist reviewers** (fan-out) | [reviewers.py](prguardian/src/prguardian/reviewers.py) | parallel security/perf/correctness/style agents |
| **Single agent** (ReAct) | [single_agent.py](prguardian/src/prguardian/single_agent.py) | interactive reviewer you can chat with |
| **Reflection / verification** | [verify.py](prguardian/src/prguardian/verify.py) | adversarial verifier drops weak findings |
| **RAG ingestion** (vector storing) | [ingest.py](prguardian/src/prguardian/ingest.py) | standards + incidents → Chroma |
| **RAG retrieval** (vector search) | [retriever.py](prguardian/src/prguardian/retriever.py) | grounding + incident similarity |
| **MCP tools** | [mcp_server/github_ci_server.py](prguardian/mcp_server/github_ci_server.py) + [tools.py](prguardian/src/prguardian/tools.py) | GitHub/CI over the Model Context Protocol |
| **Memory (short + long)** | [memory.py](prguardian/src/prguardian/memory.py) | checkpointer + self-improving feedback store |
| **Risk scoring / decision** | [risk.py](prguardian/src/prguardian/risk.py) | deterministic, auditable policy |
| **Typed guardrails** | [schemas.py](prguardian/src/prguardian/schemas.py) | Pydantic contracts for every LLM step |
| **Observability** | [observability.py](prguardian/src/prguardian/observability.py) | LangSmith + structured run log |
| **Evaluation** | [eval/run_eval.py](prguardian/eval/run_eval.py) | decision accuracy + recall on labeled PRs |
| **Models / config** | [llm.py](prguardian/src/prguardian/llm.py) + [config.py](prguardian/src/prguardian/config.py) | `claude-opus-4-8` + `claude-sonnet-4-6` |

The org-facing deck is in [PRESENTATION.md](prguardian/PRESENTATION.md); the deep
design rationale is in [ARCHITECTURE.md](prguardian/ARCHITECTURE.md).

---

## The pipeline (how the agents connect)

```
            ┌─ review_security ─┐
  intake ─▶ retrieve ─▶├─ review_performance ─┤─▶ verify ─▶ risk ─▶ human_gate ─▶ act ─▶ learn ─▶ report
 (MCP:diff   (RAG:      ├─ review_correctness ─┤  (reflection) (deterministic) (interrupt) (MCP)  (memory)
  +CI)        standards  └─ review_style ──────┘
              + similar
              incidents)         ▲ parallel fan-out, merged via a reducer
```

Each arrow is a real edge in [graph.py](prguardian/src/prguardian/graph.py). The
four reviewers run **concurrently**; `verify` waits for all of them (fan-in);
`human_gate` **pauses the whole graph** until a human responds; `learn` writes
feedback that changes how the reviewers behave next time.

---

## Where to start (reading order)

1. [config.py](prguardian/src/prguardian/config.py) — every knob in one place.
2. [schemas.py](prguardian/src/prguardian/schemas.py) — the typed contracts everything speaks.
3. [ingest.py](prguardian/src/prguardian/ingest.py) → [retriever.py](prguardian/src/prguardian/retriever.py) — RAG.
4. [mcp_server/github_ci_server.py](prguardian/mcp_server/github_ci_server.py) → [tools.py](prguardian/src/prguardian/tools.py) — MCP.
5. [reviewers.py](prguardian/src/prguardian/reviewers.py) → [verify.py](prguardian/src/prguardian/verify.py) → [risk.py](prguardian/src/prguardian/risk.py) — the review brain.
6. [memory.py](prguardian/src/prguardian/memory.py) — memory + the self-improving loop.
7. [graph.py](prguardian/src/prguardian/graph.py) — how it all wires together.
8. [cli.py](prguardian/src/prguardian/cli.py) — run it.

---

## Quickstart

```bash
cd prguardian
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env            # set ANTHROPIC_API_KEY

python -m prguardian.ingest     # build the vector store (RAG)

python examples/01_rag.py             # RAG: standards + incident similarity (no LLM)
python examples/02_single_reviewer.py # single ReAct agent
python examples/03_full_pipeline.py   # full multi-agent pipeline (auto-approves gate)
python examples/04_human_in_the_loop.py  # pause/approve + self-improving memory
python eval/run_eval.py               # measure decision accuracy + recall

python -m prguardian.cli --pr PR-4521 # interactive: pauses at the human gate
```

`PR-4521` (an export endpoint with f-string SQL + no authZ) should escalate and
flag that it **resembles INC-2024-07**. `PR-4530` (an unbounded cache) should
surface a perf finding resembling **INC-2024-11**.

> Embeddings run locally (`all-MiniLM-L6-v2`) — only `ANTHROPIC_API_KEY` is required.

---

## Why these design choices (interview answers)

- **Why a pipeline, not free-routing agents?** Review is a *bounded* workflow;
  a deterministic graph is auditable, testable, and cache-friendly. Free routing
  is reserved for the open-ended interactive reviewer.
- **Why a separate verifier?** Reviewers over-report. A skeptical verifier is
  the cheapest lever on the false-positive rate — the metric that decides
  whether engineers trust the bot or mute it.
- **Why deterministic risk scoring?** A decision that gates merges must be
  reproducible and explainable. The LLM writes the *why*; code makes the *call*.
- **Why human-in-the-loop?** No agent merges to prod unsupervised. The
  `interrupt` gate + checkpointer make every action reviewable and resumable.
- **Why self-improving memory?** Static reviewers nag. Recording accept/dismiss
  feedback lets the system converge on what *this* team actually cares about.
- **Why MCP?** One standard tool interface — swap the simulated GitHub/CI server
  for the real one and nothing in the agent code changes.
