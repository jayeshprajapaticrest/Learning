# Part II — Deep Dives: RAG Engineering, Agentic AI & LLM Ops

Part I ([README](README.md)) is the end-to-end blueprint. **Part II goes deeper** on the
specific techniques and frameworks you'll use daily — with complete feature references
for LangGraph and LangChain, advanced retrieval, and the LLM-Ops practices that keep
systems reliable.

Read Part I first for the system view; use Part II as the working reference.

---

## Track A — RAG Engineering

| # | Tutorial | Focus |
|---|----------|-------|
| 10 | [RAG Engineering Deep Dive](10-rag-engineering.md) | Component-aware chunking · hybrid (BM25+dense) · reranking · **Graph-RAG basics** · query rewriting & **multi-hop retrieval** |

## Track B — Agentic AI

| # | Tutorial | Focus |
|---|----------|-------|
| 11 | [LangGraph — Complete Feature Reference](11-langgraph-features.md) | Every LangGraph primitive for single & multi-agent systems |
| 12 | [LangChain — Complete Feature Reference](12-langchain-features.md) | Every LangChain building block for single & multi-agent systems |
| 13 | [MCP Tools & Tool-Calling Workflows](13-mcp-tool-calling.md) | Model Context Protocol + robust tool-calling loops |
| 14 | [Multi-Agent Orchestration](14-multi-agent-orchestration.md) | Supervisor, swarm, hierarchical, network patterns |

## Track C — LLM Ops

| # | Tutorial | Focus |
|---|----------|-------|
| 15 | [Prompt Engineering & Hallucination Control](15-prompt-engineering-hallucination.md) | Techniques, structure, and grounding |
| 16 | [Eval Frameworks & Synthetic Data](16-evals-synthetic-data.md) | Measuring RAG/agents + generating test/training data |

---

## How Part II relates to Part I

```
 Part I  (system blueprint)            Part II  (technique depth)
 ────────────────────────              ──────────────────────────
 T01 RAG pipeline           ───────►   T10 component chunking, multi-hop, Graph-RAG
 T04 LangGraph agents       ───────►   T11 LangGraph features  /  T14 orchestration
 (LangChain used implicitly)───────►   T12 LangChain features
 T08 MCP integration        ───────►   T13 MCP + tool-calling depth
 T06 guardrails & evals     ───────►   T15 prompt/hallucination  /  T16 evals + synth data
```

## LangGraph vs LangChain — the one-line distinction

- **LangChain** = the *component library*: models, prompts, output parsers, retrievers,
  tools, memory, and the LCEL "pipe" for composing them into chains. Great for linear,
  predictable pipelines (most RAG).
- **LangGraph** = the *orchestration framework*: a stateful graph for cyclic, branching,
  durable, multi-agent control flow. Great when you need loops, planning, human-in-the-loop,
  and recovery.

They compose: LangGraph **nodes are usually LangChain runnables**. Use LangChain to build
the pieces, LangGraph to orchestrate them when control flow gets non-linear.
