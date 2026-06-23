# RAG Engineering — Source-of-Truth Mastery Path

> A structured, production-oriented learning path for **Retrieval-Augmented Generation (RAG)**, written for an experienced Senior Software Engineer transitioning into a top-tier AI Engineer / AI Architect role.
>
> **Author stance:** Principal AI Engineer & AI Architect. Every resource listed is a *primary source* (original paper, official docs, or a well-known engineering blog from the team that built the thing). Avoid secondary "Medium summary" content except as a first gentle introduction.

---

## How to use this repo

Each module is a standalone `.md` file. They are numbered in **recommended learning order**, but ranked by **importance** below. Every module follows the same template so you can navigate quickly:

1. Why it matters in modern AI systems
2. Beginner → Intermediate → Advanced → Expert path
3. Best resources (docs / papers / blogs / books / courses / repos / talks)
4. Practical projects
5. Production architecture patterns
6. Common mistakes & anti-patterns
7. Interview-level expectations
8. Enterprise-scale considerations
9. Trade-offs & decision frameworks
10. Real-world use cases
11. Essential vs optional

### Module index

| # | Module | File | Importance |
|---|--------|------|------------|
| 1 | End-to-end RAG architectures | [01-rag-architectures.md](01-rag-architectures.md) | ⭐⭐⭐⭐⭐ Foundational |
| 2 | Chunking (smart / component-aware / semantic) | [02-chunking.md](02-chunking.md) | ⭐⭐⭐⭐⭐ Foundational |
| 3 | Retrieval: hybrid (BM25 + dense) & metadata filtering | [03-retrieval.md](03-retrieval.md) | ⭐⭐⭐⭐⭐ Foundational |
| 4 | Reranking | [04-reranking.md](04-reranking.md) | ⭐⭐⭐⭐ High ROI |
| 5 | Query transformation (rewriting / multi-query / multi-hop) | [05-query-transformation.md](05-query-transformation.md) | ⭐⭐⭐⭐ High |
| 6 | Graph-RAG | [06-graph-rag.md](06-graph-rag.md) | ⭐⭐⭐ Situational |
| 7 | Context engineering | [07-context-engineering.md](07-context-engineering.md) | ⭐⭐⭐⭐ High |
| 8 | Evaluation & observability | [08-evaluation-observability.md](08-evaluation-observability.md) | ⭐⭐⭐⭐⭐ Critical |
| 9 | Optimization techniques | [09-optimization.md](09-optimization.md) | ⭐⭐⭐⭐ High |

---

## The single most important idea

> **RAG is a search/IR problem wearing an LLM hat.** ~80% of RAG quality problems are *retrieval* problems, not generation problems. Most engineers over-invest in prompt tuning and under-invest in chunking, retrieval quality, and evaluation. **Master information retrieval (IR) fundamentals first** — they are the bedrock under every module here.

The second most important idea: **you cannot improve what you cannot measure.** Build an evaluation harness (Module 8) *before* you optimize anything. Optimizing RAG without eval is the #1 wasted-effort anti-pattern in the industry.

---

## Importance ranking & learning order (with rationale)

Ranked by leverage on real-world system quality:

1. **Evaluation & observability (Module 8)** — *Counterintuitively first in priority, even though you learn it second.* Without a test set and metrics you are flying blind. Every optimization decision is justified by this.
2. **End-to-end architectures (Module 1)** — The mental model everything else slots into. Know the canonical pipeline cold.
3. **Retrieval: hybrid + metadata (Module 3)** — The highest-leverage quality lever. Hybrid search + good filtering beats almost every "fancy" technique.
4. **Chunking (Module 2)** — Garbage chunks in → garbage retrieval out. Cheap to get wrong, cheap to fix, huge impact.
5. **Reranking (Module 4)** — Single highest precision-per-dollar improvement once basic retrieval works.
6. **Context engineering (Module 7)** — How you assemble the final prompt determines whether good retrieval actually helps. ("Lost in the middle" lives here.)
7. **Query transformation (Module 5)** — Rewriting, HyDE, multi-query, multi-hop. Big wins on hard/conversational queries.
8. **Optimization (Module 9)** — Latency, cost, caching, quantization, scaling. Matters most at enterprise scale.
9. **Graph-RAG (Module 6)** — Powerful for global/"connect-the-dots" questions but situational and operationally heavy. Learn last; deploy only when the data and questions justify it.

**Recommended *learning* sequence** (different from priority): 1 → 2 → 3 → 8 → 4 → 7 → 5 → 9 → 6. Build a working baseline (1–3), wrap it in eval (8), then layer improvements (4,7,5,9) and finally specialize (6).

---

## Prerequisites (do not skip)

Before RAG, you should be comfortable with:

- **LLM fundamentals** — tokens, context windows, temperature, embeddings vs. completions. Primary source: *Speech and Language Processing*, Jurafsky & Martin (3rd ed. draft, free: <https://web.stanford.edu/~jurafsky/slp3/>).
- **Information Retrieval basics** — TF-IDF, BM25, inverted index, precision/recall, MRR, nDCG. Primary source: *Introduction to Information Retrieval*, Manning, Raghavan, Schütze (free: <https://nlp.stanford.edu/IR-book/>). This is the most underrated book for RAG engineers.
- **Embeddings & vector similarity** — cosine vs. dot product, ANN search. Primary source: Sentence-Transformers docs (<https://www.sbert.net/>).
- **Transformers / attention** — at least conceptually. Primary source: "Attention Is All You Need" (Vaswani et al., 2017, arXiv:1706.03762) and Jay Alammar's *The Illustrated Transformer*.

---

## Foundational papers every RAG engineer must read (in order)

These are verifiable, field-defining primary sources. Read them — don't just read summaries of them.

1. **Lewis et al., 2020 — "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"** (arXiv:2005.11401). The paper that named RAG.
2. **Karpukhin et al., 2020 — "Dense Passage Retrieval for Open-Domain Question Answering" (DPR)** (arXiv:2004.04906). Why dense retrieval works.
3. **Khattab & Zaharia, 2020 — "ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT"** (arXiv:2004.12832); and **ColBERTv2** (Santhanam et al., 2021, arXiv:2112.01488). Late interaction.
4. **Gao et al., 2022 — "Precise Zero-Shot Dense Retrieval without Relevance Labels" (HyDE)** (arXiv:2212.10496).
5. **Liu et al., 2023 — "Lost in the Middle: How Language Models Use Long Contexts"** (arXiv:2307.03172). Why context order matters.
6. **Asai et al., 2023 — "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection"** (arXiv:2310.11511).
7. **Sarthi et al., 2024 — "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval"** (arXiv:2401.18059).
8. **Edge et al., 2024 — "From Local to Global: A Graph RAG Approach to Query-Focused Summarization" (Microsoft GraphRAG)** (arXiv:2404.16130).
9. **Es et al., 2023 — "RAGAS: Automated Evaluation of Retrieval Augmented Generation"** (arXiv:2309.15217).
10. **Wang et al., 2024 — "Searching for Best Practices in Retrieval-Augmented Generation"** (arXiv:2407.01219). A practical, empirical sweep of the whole pipeline.

Survey for the big picture: **Gao et al., 2023 — "Retrieval-Augmented Generation for Large Language Models: A Survey"** (arXiv:2312.10997). Read the survey *after* papers 1–4 so you have hooks to hang it on.

---

## Anthropic & frontier-lab primary references

- **Anthropic — "Introducing Contextual Retrieval" (2024)**: <https://www.anthropic.com/news/contextual-retrieval>. A must-read, results-backed technique (prepend chunk-specific context before embedding) with an open cookbook.
- **Anthropic — "Effective context engineering for AI agents"** and the **Claude Docs** prompt/tool guidance: <https://docs.claude.com>. (When building RAG on Claude, prefer the latest models — e.g. Claude Opus 4.x / Sonnet 4.x — and use prompt caching for the retrieved context; see Module 9.)
- **OpenAI cookbook** RAG examples: <https://cookbook.openai.com>.
- **Google / DeepMind** retrieval research (e.g. RETRO, REALM) for depth.

---

## Tooling landscape (official docs are the source of truth)

| Layer | Options (link to official docs) |
|-------|--------|
| Orchestration | LangChain (<https://python.langchain.com>), LlamaIndex (<https://docs.llamaindex.ai>), Haystack (<https://docs.haystack.deepset.ai>), DSPy (<https://dspy.ai>) |
| Vector DBs | pgvector (<https://github.com/pgvector/pgvector>), Qdrant (<https://qdrant.tech/documentation/>), Weaviate (<https://weaviate.io/developers/weaviate>), Milvus (<https://milvus.io/docs>), Pinecone (<https://docs.pinecone.io>), Elasticsearch/OpenSearch vector search |
| Embeddings | OpenAI `text-embedding-3`, Cohere `embed v3`, Voyage AI, BAAI `bge` family, `sentence-transformers` |
| Rerankers | Cohere Rerank, BGE-reranker, Jina reranker, `cross-encoder` models, ColBERT |
| Eval | RAGAS (<https://docs.ragas.io>), TruLens, DeepEval, Arize Phoenix, LangSmith |
| Observability | LangSmith, Arize Phoenix, Langfuse, OpenLLMetry / OpenTelemetry GenAI semantic conventions |

> **Decision principle:** Start boring. `pgvector` + BM25 (Postgres or OpenSearch) + a reranker + RAGAS covers ~90% of enterprise needs and keeps everything in systems your ops team already runs. Reach for a dedicated vector DB when scale (>10–50M vectors), latency SLOs, or advanced filtering force the issue (see Module 9).

---

## Mastery roadmaps

These assume ~8–10 focused hrs/week alongside a full-time job. Adjust to your pace.

### 6-Month roadmap — "Ship a production-grade RAG service"

**Goal:** You can independently design, build, evaluate, and deploy a non-trivial RAG application end to end.

- **Month 1 — Foundations.** IR basics (BM25, nDCG/MRR), embeddings, read RAG/DPR papers. Build a naive RAG over your own docs (LlamaIndex or LangChain + pgvector). Module 1, 2.
- **Month 2 — Retrieval quality.** Implement hybrid search (BM25 + dense) and metadata filtering. Add a cross-encoder reranker. Modules 3, 4.
- **Month 3 — Evaluation.** Build a golden test set (50–200 Q/A pairs). Wire up RAGAS + a retrieval-metrics harness (recall@k, nDCG). Establish a baseline scoreboard. Module 8. *This is the inflection point of the whole journey.*
- **Month 4 — Chunking & context.** Experiment with semantic and component-aware chunking; Contextual Retrieval; tackle "lost in the middle" via reordering/compression. Modules 2, 7.
- **Month 5 — Query handling & optimization.** Query rewriting, multi-query, HyDE. Add caching, measure & cut latency/cost. Modules 5, 9.
- **Month 6 — Productionize.** Observability (tracing, dashboards), guardrails, an offline eval CI gate, a deployment. Ship it. Write it up. Modules 8, 9.

**Capstone:** A deployed RAG app with a documented eval scoreboard showing measured improvements over the naive baseline.

### 12-Month roadmap — "Senior RAG / Applied AI Engineer"

Builds on the 6-month base.

- **Months 7–8 — Advanced retrieval & rerank.** ColBERT/late interaction, multi-vector, matryoshka/quantized embeddings, fine-tuning an embedding model on your domain. Multi-hop retrieval. Modules 3, 4, 5.
- **Months 9–10 — Graph-RAG & agentic RAG.** Microsoft GraphRAG, knowledge-graph construction, agentic/iterative retrieval (self-RAG, corrective RAG), DSPy for compiled pipelines. Modules 6, 5, 1.
- **Months 11–12 — Enterprise hardening.** Multi-tenancy & data isolation, security (prompt injection via retrieved content, ACL-aware retrieval), governance, PII handling, cost modeling, SLOs, autoscaling, incremental indexing pipelines. Modules 9 + cross-cutting.

**Capstone:** A multi-tenant, access-controlled RAG platform component with CI eval gates, full observability, and a written architecture decision record (ADR) set.

### 18-Month roadmap — "Principal / AI Architect"

- **Months 13–15 — Research depth & SOTA tracking.** Reproduce key papers; run controlled experiments; build an internal RAG benchmark; contribute to OSS (LangChain/LlamaIndex/RAGAS) or publish. Track new SOTA via arXiv `cs.IR`/`cs.CL`, ACL/EMNLP/SIGIR/NeurIPS.
- **Months 16–18 — Platform & org leverage.** Design a reusable RAG platform: shared ingestion, embedding-as-a-service, eval-as-a-service, golden datasets governance, model-router, cost/latency tiering, and an internal "RAG paved road." Mentor; set standards; write the org's RAG design guidelines. Drive build-vs-buy decisions.

**Capstone:** An org-level RAG platform design + governance framework + an internal benchmark others build on. You are now the person other teams consult.

---

## Anti-patterns to internalize early (the "do not" list)

1. **No evaluation set.** Tuning by vibes. Fix: Module 8 first.
2. **Naive fixed-size chunking with no overlap and no structure awareness.** Module 2.
3. **Dense-only retrieval** (ignoring BM25/keywords). Hybrid almost always wins. Module 3.
4. **No reranking** when precision matters. Module 4.
5. **Stuffing top-k blindly** into the prompt, ignoring "lost in the middle." Module 7.
6. **Treating retrieved content as trusted** → indirect prompt injection. Cross-cutting security; see Modules 1 & 9.
7. **Reaching for Graph-RAG / agents before nailing hybrid + rerank + eval.** Module 6.
8. **Ignoring metadata/ACLs** → data leakage across tenants/users. Modules 3 & 9.

---

## A note on staying current (avoiding outdated resources)

RAG moves fast. To keep this path "source of truth":

- Track **arXiv** `cs.IR`, `cs.CL`, `cs.LG` (use a tool like arXiv Sanity or Semantic Scholar alerts).
- Follow primary engineering blogs: Anthropic, OpenAI, Cohere, Pinecone, Weaviate, Qdrant, LlamaIndex, LangChain, deepset (Haystack), Vespa.
- Conferences for the real signal: **SIGIR, ACL, EMNLP, NeurIPS, ICLR**; for applied/eng: company tech blogs and the **MLOps Community**.
- Prefer dated, versioned official docs. When a blog post is >18 months old, verify the technique against current docs before adopting.

> Treat any single tool's "best practices" page as *that vendor's* opinion. Cross-check against papers and at least one neutral source.
