# Module 1 — End-to-End RAG Architectures

> The mental model every other module plugs into. If you internalize one diagram in this entire repo, make it the canonical RAG pipeline below.

---

## 1. Why it matters

RAG exists to solve a hard, permanent problem: **LLMs have a fixed training cutoff, no access to private/enterprise data, and hallucinate confidently.** RAG grounds generation in retrieved, attributable, up-to-date evidence — without retraining the model. It is the dominant pattern for enterprise AI because it is:

- **Cheaper** than fine-tuning for knowledge injection, and updatable in seconds (re-index vs. re-train).
- **Attributable** — you can cite sources, which is mandatory for regulated industries.
- **Controllable** — access control, freshness, and correctness live in the retrieval layer you own.

Knowing the *architecture* end to end is what separates someone who can call an SDK from someone who can diagnose *where* in the pipeline quality is being lost.

---

## 2. The canonical pipeline (know this cold)

RAG has two phases. Conflating them is the most common conceptual error.

### A. Indexing / ingestion (offline, batch)
```
Source data → Load/parse → Clean/normalize → Chunk → Enrich (metadata, context)
            → Embed → Upsert into vector store + keyword index
```

### B. Query / serving (online, per request)
```
User query → (optional) Query transformation → Retrieve (dense + sparse)
           → Rerank → Assemble context (dedup, compress, order)
           → Prompt construction → LLM generation → Post-process (cite, guardrail)
           → Response (+ traces/metrics)
```

Each box maps to a module: chunk→M2, retrieve→M3, rerank→M4, query transform→M5, assemble→M7, everything measured by→M8, everything tuned for cost/latency by→M9.

---

## 3. Architecture variants (a maturity ladder)

| Level | Name | What it adds | When to use |
|-------|------|--------------|-------------|
| 0 | **Naive / "vanilla" RAG** | Chunk → embed → top-k cosine → stuff into prompt | Prototype, demo |
| 1 | **Hybrid RAG** | + BM25, + metadata filters, + reranker | The sane production baseline |
| 2 | **Advanced RAG** | + query transformation, + context compression, + parent-doc / small-to-big retrieval | Quality-sensitive prod |
| 3 | **Modular / Compiled RAG** | Pipeline of swappable modules; DSPy-style optimized prompts | Teams that A/B and optimize systematically |
| 4 | **Agentic / Iterative RAG** | LLM decides *whether/what/when* to retrieve; multi-step (Self-RAG, Corrective RAG, ReAct-style) | Complex, multi-hop, tool-using tasks |
| 5 | **GraphRAG** | Knowledge graph + community summaries for global questions | Connect-the-dots / summarization over a corpus (Module 6) |

> **The "naive → advanced" framing** comes from Gao et al.'s RAG survey (arXiv:2312.10997), which organizes the field into *Naive*, *Advanced*, and *Modular* RAG. Read it once you have a baseline running.

### Notable named architectures (primary sources)
- **Self-RAG** (Asai et al., 2023, arXiv:2310.11511) — model emits reflection tokens to decide when to retrieve and to critique its own output.
- **Corrective RAG / CRAG** (Yan et al., 2024, arXiv:2401.15884) — a lightweight retrieval evaluator triggers web search / correction when retrieved docs are weak.
- **RAPTOR** (Sarthi et al., 2024, arXiv:2401.18059) — recursively cluster+summarize chunks into a tree; retrieve at multiple abstraction levels.
- **FLARE** (Jiang et al., 2023, arXiv:2305.06983) — actively retrieve mid-generation when the model is uncertain.
- **REALM** (Guu et al., 2020, arXiv:2002.08909) and **RETRO** (Borgeaud et al., 2021, arXiv:2112.04426) — retrieval baked into pretraining (depth/context, not day-to-day eng).

---

## 4. Learning path

### Beginner
- Build naive RAG over ~50 of your own PDFs/markdown docs using **LlamaIndex** ([starter tutorial](https://docs.llamaindex.ai)) or **LangChain** ([RAG tutorial](https://python.langchain.com/docs/tutorials/rag/)).
- Understand each pipeline stage by printing intermediate outputs (the chunks, the retrieved set, the final prompt).
- Read the original **RAG paper** (Lewis et al., 2020) and the **Gao survey** intro.

### Intermediate
- Re-implement the pipeline *without* a heavy framework — raw embeddings API + pgvector + your own prompt assembly — so you understand what the framework hides.
- Add the Level-1 components (hybrid, filter, rerank).
- Read **"Searching for Best Practices in RAG"** (Wang et al., 2024, arXiv:2407.01219) and adopt its empirically-supported defaults.

### Advanced
- Implement an **agentic RAG** loop (retrieve → grade → decide to re-retrieve / rewrite / answer). Study **Self-RAG** and **CRAG**.
- Use **DSPy** (<https://dspy.ai>) to express the pipeline as modules and *compile* prompts against your metric instead of hand-tuning.
- Implement **small-to-big / parent-document retrieval** and **RAPTOR**.

### Expert
- Design a **modular RAG platform**: pluggable retrievers/rerankers/generators behind interfaces, per-query routing (cheap path vs. expensive path), and a feedback loop where production traces feed eval sets.
- Own build-vs-buy, multi-region, and cost/latency tiering decisions (Module 9).

---

## 5. Best resources

- **Papers:** Lewis 2020 (2005.11401); Gao survey (2312.10997); Self-RAG (2310.11511); CRAG (2401.15884); RAPTOR (2401.18059); Best-Practices (2407.01219).
- **Docs:** LlamaIndex *Understanding RAG* & high-level concepts; LangChain RAG tutorial + *Conceptual guide*; Haystack pipelines docs; DSPy docs.
- **Courses:** DeepLearning.AI short courses — *"Building and Evaluating Advanced RAG"* (with LlamaIndex/TruLens) and *"Preprocessing Unstructured Data for LLM Applications."* Free, high signal.
- **Talks:** Jerry Liu (LlamaIndex) and Harrison Chase (LangChain) conference talks on advanced/agentic RAG; Jo Bergum (Vespa) talks on retrieval at scale.
- **Repos:** `run-llama/llama_index`, `langchain-ai/langchain`, `deepset-ai/haystack`, `stanfordnlp/dspy`, and `langchain-ai/rag-from-scratch` (excellent annotated notebooks).

---

## 6. Production architecture patterns

- **Separate ingestion and serving** as distinct services/pipelines with their own scaling and SLOs. Ingestion is batch/streaming; serving is low-latency online.
- **Incremental indexing.** Use content hashing + upsert so re-ingesting a corpus only re-embeds changed chunks. Maintain a document→chunk→vector lineage table.
- **Embedding-as-a-service.** Centralize embedding behind one internal endpoint so model version, dimension, and batching are controlled in one place (critical — see anti-patterns).
- **Router pattern.** Classify the query (or use heuristics) to pick the cheap path (single retrieve + small model) vs. expensive path (rewrite + multi-query + rerank + large model).
- **Cache layers.** Exact-match and semantic caching of (query → answer) and (query → retrieved set). See Module 9.
- **Two-stage retrieve-then-rerank** is the default high-quality serving shape.

---

## 7. Common mistakes & anti-patterns

- **Re-embedding with a different model than the index was built with.** Vectors become meaningless. Pin embedding model + version to the index; re-index fully on change.
- **Mixing indexing and query embedding asymmetry incorrectly** (e.g., using an instruction-tuned query prefix at index time). Follow the embedding model's documented query/passage convention exactly.
- **No source attribution / citations**, blocking adoption in regulated settings.
- **Treating RAG as a prompt problem.** When answers are wrong, inspect retrieval first (was the right chunk even in the candidate set?).
- **Premature agentic/graph complexity** before the Level-1 baseline + eval exist.
- **No idempotent, incremental ingestion** → full re-index every change, expensive and slow.

---

## 8. Interview-level expectations

You should be able to, on a whiteboard:
- Draw the full indexing + serving pipeline and name failure modes at each stage.
- Explain RAG vs. fine-tuning vs. long-context-stuffing and when each wins (knowledge freshness/attribution → RAG; behavior/format/style → fine-tune; small bounded context → long-context).
- Explain the retrieve-then-rerank two-stage pattern and why it beats single-stage.
- Describe how you'd debug "the answer is wrong" systematically (retrieval recall? rerank? context order? generation?).
- Sketch an agentic RAG loop and explain when the added latency/cost is justified.

---

## 9. Enterprise-scale considerations

- **Access control:** retrieval must be ACL-aware — filter by the requesting user's permissions *at query time* (never rely on the LLM to withhold). Store ACL metadata on chunks.
- **Multi-tenancy:** namespace/partition per tenant; verify no cross-tenant leakage in eval.
- **Freshness SLAs:** define how fast a source change must appear in answers; design the ingestion pipeline (CDC/streaming) to meet it.
- **Auditability:** log query, retrieved doc IDs, model version, and final answer for every request (compliance + debugging + future eval data).
- **Security:** retrieved content is **untrusted input** → it can carry indirect prompt injection. Treat it as data, sandbox tool use, and apply output guardrails.

---

## 10. Trade-offs & decision frameworks

| Decision | Lever | Rule of thumb |
|----------|-------|---------------|
| RAG vs. fine-tune vs. long-context | Cost, freshness, attribution | RAG for knowledge & citations; fine-tune for behavior; long-context only for small, bounded docs |
| Framework vs. from-scratch | Velocity vs. control | Prototype with a framework; for core platform, own the critical path |
| Naive vs. agentic | Latency/cost vs. accuracy on hard queries | Add agentic only where eval shows multi-hop/uncertain queries failing |
| Sync vs. streaming ingestion | Freshness SLA | Streaming/CDC when minutes matter; batch otherwise |

---

## 11. Real-world use cases

- **Enterprise knowledge assistants / internal search** (the canonical use case across virtually every large company).
- **Customer support copilots** grounded in product docs + ticket history.
- **Coding assistants** retrieving from a codebase/docs (e.g., repo-aware code Q&A).
- **Legal / financial / healthcare** document Q&A where citations and access control are mandatory.
- **Perplexity-style answer engines** combining web retrieval + generation with citations.

---

## 12. Essential vs optional

- **Essential:** the canonical pipeline; naive→hybrid→advanced ladder; retrieve-then-rerank; ingestion vs. serving separation; ACL-aware retrieval.
- **Optional / situational:** agentic loops, GraphRAG, retrieval-in-pretraining (REALM/RETRO). Learn the concepts; deploy only when eval justifies the complexity.

---

### Capstone project for this module
Build the *same* corpus three ways — naive, hybrid, and agentic — behind one interface, and produce a one-page comparison of quality (Module 8 metrics), latency, and cost. This single exercise teaches more than any course.
