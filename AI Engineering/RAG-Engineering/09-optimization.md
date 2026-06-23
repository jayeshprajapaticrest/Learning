# Module 9 — RAG Optimization Techniques (Latency, Cost, Scale, Quality)

> Once RAG *works* and is *measured*, optimization is about moving along three axes — **quality, latency, and cost** — under enterprise constraints (scale, reliability, security, governance). This module is the bridge from "works on my laptop" to "serves the org at SLO."

---

## 1. Why it matters

A correct-but-slow-and-expensive RAG system doesn't ship. At enterprise scale the constraints bite hard:

- **Latency SLOs** — users abandon slow assistants; each pipeline hop (rewrite, retrieve, rerank, generate) adds time.
- **Cost** — embeddings at ingest, vector RAM, reranker GPUs, and (dominant) LLM generation tokens add up fast at millions of queries.
- **Scale** — 10M → 1B+ vectors changes every storage/indexing decision.
- **Reliability & security** — multi-tenancy, ACLs, prompt-injection defense, graceful degradation.

Optimization is always a **trade-off negotiation against your eval scoreboard (Module 8)** — never optimize one axis blind to the others.

---

## 2. The optimization map

### Quality levers (recap — see other modules)
Chunking (M2), hybrid + filtering (M3), reranking (M4), query transformation (M5), context engineering (M7), domain-tuned embeddings (M3). **Always validate quality changes against eval.**

### Latency levers
- **Parallelize** independent stages (dense + sparse retrieval concurrently; multi-query fan-out in parallel).
- **Two-stage sizing** — retrieve fewer candidates / rerank fewer when latency-bound; batch reranker forward passes.
- **Streaming** the LLM response (improves perceived latency / TTFT).
- **Smaller/faster models** on the cheap path (router); reserve large models for hard queries.
- **ANN tuning** (HNSW `ef_search`) for the recall/latency knee.
- **Caching** (below) — the biggest latency win for repeated traffic.
- **Co-locate** services / reduce network hops; warm pools for embedding & reranker.

### Cost levers
- **Prompt caching** (Anthropic/OpenAI) for stable prefixes (system prompt, static/long context, tool defs) — large savings on repeated calls. Structure prompts so cacheable content comes first (Module 7).
- **Semantic + exact caching** of (query→answer) and (query→retrieved set). A semantic cache (embedding-similarity match) catches paraphrased repeats.
- **Model tiering / routing** — cheap model for easy queries, expensive only when needed.
- **Embedding cost control** — batch embeddings; cache; **quantization** and **Matryoshka** (truncatable) dims to shrink vector storage; smaller embedding models where eval permits.
- **Context compression** (LLMLingua / extractive filtering, Module 7) to cut input tokens.
- **Batch APIs** for non-realtime ingestion/eval.

### Scale levers (vector infra)
- **Quantization:** Product Quantization (PQ), Scalar Quantization (SQ), and **binary quantization** cut RAM 4–32× with measurable recall trade-offs (Qdrant/Weaviate/Milvus support these). FAISS IVF-PQ for billion-scale.
- **Sharding & replication:** shard by tenant/doc-space for isolation + parallelism; replicas for QPS and HA.
- **Tiered storage:** hot vectors in RAM, cold on disk/SSD (e.g., DiskANN-style, Milvus/Qdrant on-disk modes).
- **Incremental indexing:** content-hash + upsert; only re-embed changed chunks; tombstones for deletes.
- **Index lifecycle:** blue/green re-index for embedding-model upgrades; versioned indexes.

### Generation-quality/efficiency levers
- **Prompt caching + structured output** to reduce retries.
- **Self-correction / CRAG** only where eval shows it's worth the cost.
- **Speculative decoding / smaller distilled models** for self-hosted serving.

---

## 3. Learning path

### Beginner
- Add **exact-match caching** and measure latency/cost reduction. Stream responses.
- Profile per-stage latency and token/cost per query (ties to Module 8 observability).

### Intermediate
- Add **semantic caching** and **prompt caching**. Implement a simple **router** (cheap vs. expensive path).
- Apply **vector quantization** and measure recall vs. RAM/cost.

### Advanced
- Implement **model tiering**, **context compression at scale**, and **autoscaling** for embedding/reranker/LLM services.
- Design **incremental + blue/green re-indexing**; load-test at 10–100× data.
- Fine-tune/distill smaller models for the cheap path.

### Expert
- Design a **cost/latency tiering architecture** with SLOs per tier; capacity planning and $/query modeling.
- Billion-scale vector serving: sharding topology, quantization strategy, tiered storage, recall SLO governance.
- Build a **RAG platform**: embedding-as-a-service, eval-as-a-service, model router, shared caching, multi-tenant isolation, and a paved-road SDK.

---

## 4. Best resources

- **Papers/methods:** Matryoshka Representation Learning (2205.13147); LLMLingua/LongLLMLingua (2310.05736/2310.06839); Product Quantization (Jégou et al., 2011); HNSW (1603.09320); DiskANN (Subramanya et al., NeurIPS 2019); FrugalGPT (Chen et al., 2023, arXiv:2305.05176) for model cascades/routing.
- **Docs/blogs:** Anthropic & OpenAI **prompt caching** docs (docs.claude.com / platform.openai.com); Qdrant, Weaviate, Milvus **quantization** & scaling docs; Pinecone scaling guides; Vespa blog (retrieval at scale); FAISS wiki; vector-DB benchmark `ann-benchmarks.com`.
- **Repos:** `facebookresearch/faiss`, `microsoft/DiskANN`, `qdrant/qdrant`, `milvus-io/milvus`, `microsoft/LLMLingua`, `BerriAI/litellm` (model routing/gateway), `zilliztech/GPTCache` (semantic cache).
- **Courses:** DeepLearning.AI *"Building and Evaluating Advanced RAG"*; MLOps/LLMOps community talks on serving & cost.

---

## 5. Production architecture patterns

- **Router + tiered models:** classify → cheap path (small model, single retrieve) or expensive path (rewrite + multi-query + rerank + large model).
- **Multi-layer cache:** exact → semantic → prompt cache, with TTLs and invalidation on re-index.
- **Embedding-as-a-service** and **rerank-as-a-service** (batched, autoscaled GPU pools, pinned versions).
- **Async/streaming ingestion** (CDC/queues) with incremental upsert and lineage tables.
- **Blue/green index migration** for model upgrades; canary + online eval before promotion.
- **Graceful degradation:** if rerank/LLM is overloaded, fall back to retrieval-only or cached answers rather than failing.
- **Multi-tenant isolation:** namespace/shard per tenant; mandatory server-side ACL filters.

---

## 6. Common mistakes & anti-patterns

- **Optimizing without eval** → shipping silent quality regressions to save latency/cost.
- **Premature optimization** before there's traffic or a measured bottleneck.
- **No caching** despite high repeat-query rates (leaving the easiest win on the table).
- **Aggressive quantization** without measuring recall loss.
- **One model for everything** (over-paying on easy queries; under-serving hard ones).
- **Full re-index on every change** instead of incremental upsert.
- **Volatile-before-stable prompt layout** → zero prompt-cache hits.
- **Ignoring tail latency (p95/p99)** and capacity limits until an incident.
- **Cache invalidation bugs** serving stale answers after a re-index (and stale ACLs → leakage).

---

## 7. Interview-level expectations

- Walk the **quality/latency/cost triangle** and name the lever for each, with trade-offs.
- Explain prompt caching, semantic caching, and model routing/cascades (FrugalGPT idea).
- Explain vector quantization (PQ/SQ/binary) and the recall trade-off; HNSW vs. IVF-PQ vs. DiskANN at scale.
- Design incremental + blue/green re-indexing and explain cache invalidation correctness.
- Reason about p95 latency budgets across pipeline stages and where to cut.
- Describe multi-tenant isolation and ACL enforcement under optimization pressure.

---

## 8. Enterprise-scale considerations

- **$/query and $/M-docs modeling** for ingest (embeddings) + storage (vector RAM) + serving (rerank GPU + LLM tokens).
- **SLOs & capacity planning:** define p95 latency and availability per tier; autoscale; load-test to peak.
- **Reliability:** retries, timeouts, circuit breakers, graceful degradation, multi-region/DR.
- **Security & governance:** prompt-injection defense on retrieved content; output guardrails; PII redaction; audit logs; data residency; ACL freshness on re-index.
- **FinOps:** cache hit-rate dashboards, model-cost attribution per team/tenant, budget alerts.

---

## 9. Trade-offs & decision framework

```
High repeat traffic?              → caching first (exact → semantic → prompt). Biggest cheap win.
Latency-bound?                    → parallelize stages, stream, smaller candidate sets, route to small model.
Cost-bound?                       → prompt caching + model tiering + context compression + cheaper embeddings.
RAM/scale-bound (>50M vectors)?   → quantization + sharding + tiered/on-disk storage.
Quality-bound?                    → revisit Modules 2–7; spend latency/cost only where eval shows it pays.

Golden rule: every optimization is A/B'd against the eval scoreboard. No metric, no merge.
```

---

## 10. Real-world use cases

- **High-QPS support/search assistants** — caching + routing + streaming to hit latency SLOs at low cost.
- **Billion-vector enterprise search** — quantization + sharding + tiered storage.
- **Cost-sensitive consumer apps** — model cascades (FrugalGPT-style) + semantic cache.
- **Regulated platforms** — optimization constrained by ACL freshness, audit, residency, and guardrails.

---

## 11. Essential vs optional

- **Essential:** caching (exact + prompt), per-stage latency/cost profiling, model routing, incremental indexing, eval-gated changes, ACL-safe multi-tenancy.
- **High-ROI:** semantic caching, vector quantization, context compression, streaming, autoscaling.
- **Optional / situational:** billion-scale sharding/tiered storage, distilled/speculative serving, full platform-ization — at large scale / platform maturity.

---

### Capstone project for this module
Take your working RAG service and produce a **before/after optimization report**: add multi-layer caching, model routing, quantization, and prompt caching; then chart quality (eval scoreboard), p50/p95 latency, and $/query before vs. after — proving you cut cost/latency **without** regressing quality. Include a $/M-docs ingest model and an SLO/capacity plan. This is exactly the artifact a Principal AI Engineer is expected to produce.
