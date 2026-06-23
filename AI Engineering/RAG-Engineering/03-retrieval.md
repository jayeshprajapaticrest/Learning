# Module 3 — Retrieval: Hybrid Search (BM25 + Dense) & Metadata Filtering

> The single highest-leverage quality lever in RAG. Most teams over-invest in prompts and under-invest here. **Hybrid retrieval + good metadata filtering beats almost every "advanced" technique** you can bolt on later.

---

## 1. Why it matters

Retrieval determines the **ceiling** of your system: if the right evidence isn't in the candidate set, no reranker, no clever prompt, and no bigger model can save the answer. There are two complementary retrieval paradigms, and each fails where the other succeeds:

- **Sparse / lexical (BM25):** matches exact terms. Unbeatable for **rare keywords, codes, IDs, names, acronyms, error strings** ("error TS2304", "form 1099-B", a SKU). Fails on synonyms/paraphrase ("car" vs "automobile").
- **Dense / semantic (embeddings + ANN):** matches *meaning*. Great for paraphrase and concept queries. Fails on exact-token needs and out-of-distribution jargon, and silently returns "semantically near but wrong" results.

**Hybrid search runs both and fuses the results**, capturing exact-match precision *and* semantic recall. This is why it is the production baseline. Metadata filtering then constrains the search space for correctness (freshness, tenant, ACL, doc type) and speed.

---

## 2. Core concepts

### BM25 (the sparse workhorse)
A bag-of-words ranking function (Robertson & Spärck Jones; the field standard) scoring term frequency × inverse document frequency with document-length normalization (`k1`, `b` params). It is a *strong, cheap, tunable baseline* — modern dense retrievers still struggle to beat well-tuned BM25 on keyword-heavy domains. Available in Elasticsearch/OpenSearch/Lucene, and as `rank-bm25` / `bm25s` in Python. **Variant:** SPLADE (Formal et al., arXiv:2107.05720) — *learned sparse* retrieval that adds term expansion, getting semantic benefits while keeping inverted-index efficiency.

### Dense retrieval (the semantic workhorse)
Encode query and passages into vectors; retrieve nearest neighbors. Foundations: **DPR** (Karpukhin et al., 2020, arXiv:2004.04906). Key sub-decisions:
- **Embedding model:** OpenAI `text-embedding-3-large/small`, Cohere `embed-v3`, Voyage AI, BAAI `bge-*`, `e5`, GTE. Track the **MTEB leaderboard** (<https://huggingface.co/spaces/mteb/leaderboard>) — the standard benchmark (Muennighoff et al., arXiv:2210.07316) — but **always re-validate on your domain**; leaderboard rank ≠ your-corpus rank.
- **Bi-encoder vs. cross-encoder vs. late-interaction:** bi-encoder (separate vectors, fast, used for first-stage retrieval) vs. cross-encoder (joint, accurate, slow — used for *reranking*, Module 4) vs. **ColBERT** late interaction (token-level multi-vector; arXiv:2004.12832 / v2 2112.01488) — accuracy near cross-encoders with retrieval-scale efficiency.
- **Asymmetric encoding:** many models use distinct query vs. passage prefixes/instructions. Follow the model card exactly or you silently lose quality.

### ANN indexing (how vectors are searched fast)
Exact kNN is O(N); production uses **Approximate Nearest Neighbor**:
- **HNSW** (Malkov & Yashunin, arXiv:1603.09320) — graph-based, the most common; tune `M`, `ef_construction`, `ef_search` (recall vs. latency/memory).
- **IVF / IVF-PQ** (FAISS) — inverted-file + product quantization for memory-efficient billion-scale search.
- Trade-off: ANN trades a little recall for huge speed; *measure* the recall loss against exact search on a sample.

### Hybrid fusion (how to combine BM25 + dense)
- **Reciprocal Rank Fusion (RRF)** — Cormack et al., 2009. `score = Σ 1/(k + rank_i)` across result lists. **Rank-based, no score normalization needed, robust, the de-facto default.** Built into Elasticsearch, OpenSearch, Weaviate, Qdrant, Milvus.
- **Weighted score fusion / convex combination** — normalize then `α·dense + (1−α)·sparse`. Needs score normalization (min-max); `α` is tunable per domain.
- **Relative score fusion** (Weaviate) — normalizes then weights.

> **Default recommendation:** BM25 + dense, fused with **RRF**, then a **reranker** (Module 4). This stack is the empirically supported sweet spot (see Wang et al. 2024, arXiv:2407.01219, and Anthropic Contextual Retrieval results).

### Metadata filtering
Attach structured fields to every chunk (`tenant_id`, `acl/principals`, `doc_type`, `source`, `date`, `language`, `version`, `section_path`) and filter at query time.
- **Pre-filter** (filter then search): correct & secure, but can hurt ANN performance/recall if the filter is very selective (small candidate pool breaks the ANN graph). Modern engines (Qdrant, Weaviate, Milvus, pgvector + indexes) support efficient **filtered ANN**.
- **Post-filter** (search then filter): simple but can return too few results; avoid for security filters.
- **Security-critical filters (ACL, tenant) MUST be enforced server-side, pre-search, never optionally.**

---

## 3. Learning path

### Beginner
- Read *Introduction to Information Retrieval* (Manning et al.) chapters on the inverted index, TF-IDF, BM25, and evaluation. Implement BM25 with `rank-bm25`.
- Build dense retrieval with `sentence-transformers` + a vector DB. Read **DPR**.

### Intermediate
- Implement **hybrid search with RRF** and measure the lift over dense-only and BM25-only on your eval set.
- Implement **metadata pre-filtering** (date, type, tenant).
- Learn HNSW params and measure the recall/latency curve.

### Advanced
- Fine-tune or domain-adapt an embedding model (contrastive learning with hard negatives; `sentence-transformers` training). Use **ColBERTv2** for hard domains.
- Implement **filtered ANN** correctly for a multi-tenant, ACL-enforced corpus.
- Experiment with **SPLADE** / learned sparse and **Matryoshka** embeddings (truncatable dimensions, arXiv:2205.13147) for cost control.

### Expert
- Design retrieval for **100M–1B+ vectors**: sharding, quantization (PQ/SQ/binary), tiered storage, replica topology, recall SLOs.
- Build an **embedding model lifecycle**: periodic re-evaluation, controlled re-embedding/migration, A/B of embedding models in production.

---

## 4. Best resources

- **Books:** *Introduction to Information Retrieval* (Manning, Raghavan, Schütze — free online). The IR bible.
- **Papers:** DPR (2004.04906); ColBERT/v2 (2004.12832 / 2112.01488); SPLADE (2107.05720); HNSW (1603.09320); MTEB (2210.07316); Matryoshka embeddings (2205.13147); RRF (Cormack et al., 2009, SIGIR).
- **Docs/blogs:** Pinecone *Learn* hub (excellent free IR/vector course); Weaviate, Qdrant, Milvus, Elasticsearch hybrid-search docs; Cohere/Voyage/OpenAI embedding docs; Vespa blog (Jo Bergum) for retrieval-at-scale depth.
- **Leaderboards:** MTEB (embeddings); BEIR benchmark (Thakur et al., arXiv:2104.08663) for zero-shot retrieval generalization.
- **Repos:** `facebookresearch/faiss`, `stanford-futuredata/ColBERT`, `naver/splade`, `UKPLab/sentence-transformers`, `castorini/pyserini` (BM25 + dense IR toolkit, great for learning).

---

## 5. Production architecture patterns

- **Two indexes, one query path:** inverted index (BM25) + vector index (HNSW). Some engines (OpenSearch, Weaviate, Qdrant, pgvector + tsvector) host both; otherwise query in parallel and fuse with RRF in your service.
- **Filtered ANN with mandatory security filters** injected by the service, not the caller.
- **Embedding-as-a-service** with pinned model+version and request batching.
- **Read replicas / sharding** by tenant or document space for scale and isolation.
- **Index versioning + blue/green re-index** for embedding-model migrations (build new index alongside, switch read traffic, then retire old).

---

## 6. Common mistakes & anti-patterns

- **Dense-only retrieval.** The most common quality bug. Add BM25.
- **Ignoring the embedding model's query/passage convention** (prefixes/instructions).
- **Tuning `α` weights or fusion without an eval set.**
- **Over-aggressive ANN params** sacrificing recall invisibly (you never see the docs you missed).
- **Post-filtering security/ACL constraints** → leakage or empty results.
- **Mixing embedding models / dimensions in one index.**
- **Forgetting BM25 is a strong baseline** — and skipping it because "embeddings are modern."
- **No re-embedding plan** when you upgrade the embedding model.

---

## 7. Interview-level expectations

- Explain BM25 vs. dense and give concrete queries where each wins.
- Explain hybrid search and **why RRF is preferred** (rank-based, no score-scale mismatch).
- Explain HNSW vs. IVF-PQ and the recall/latency/memory trade-off.
- Explain bi-encoder vs. cross-encoder vs. ColBERT and where each sits in the pipeline.
- Explain pre- vs. post-filtering and why ACL filters must be pre-filtered server-side.
- Define and compute recall@k, MRR, nDCG (ties into Module 8).

---

## 8. Enterprise-scale considerations

- **Cost:** vector memory dominates at scale; quantization (PQ, scalar, binary) and Matryoshka dims cut RAM/cost dramatically — measure recall impact.
- **Latency SLOs:** hybrid + rerank adds hops; budget per stage; use ANN tuning, caching, and parallel sparse/dense calls.
- **Multi-tenancy & isolation:** partition strategy (namespace vs. shared-with-filter) is a security *and* performance decision.
- **Data residency / compliance:** region-pinned indexes; on-prem/self-hosted embeddings when data can't leave.
- **Freshness:** incremental upsert + tombstones for deletes; reflect ACL changes promptly (stale ACLs = leakage).

---

## 9. Trade-offs & decision framework

```
Need exact-term matching (codes, names, jargon)?      → must include BM25/sparse.
Need synonym/paraphrase/concept matching?             → must include dense.
Almost always?                                        → HYBRID (BM25 + dense + RRF).

Choosing a vector store:
  < a few M vectors, want one system     → pgvector (Postgres) or OpenSearch.
  Need rich filtered ANN + scale          → Qdrant / Weaviate / Milvus.
  Managed, don't want ops                 → Pinecone (or managed Weaviate/Qdrant).
  Already deep in Elastic/OpenSearch      → use its native hybrid.

Recall vs. latency/memory  → tune HNSW (M, ef) / quantize; validate recall vs. exact.
Generic vs. domain embeddings → start generic (top MTEB); fine-tune when eval plateaus.
```

---

## 10. Real-world use cases

- **Enterprise search** across wikis/tickets/docs — hybrid is non-negotiable (lots of exact terms + concepts).
- **E-commerce / product search** — dense for "warm waterproof jacket", BM25 for SKUs/brands; fusion + filters (price, category).
- **Code & log search** — BM25-heavy (identifiers, error codes) augmented with dense.
- **Legal/financial** — strict metadata filtering (jurisdiction, date, entity) + hybrid + ACLs.

---

## 11. Essential vs optional

- **Essential:** BM25, dense retrieval, hybrid + RRF, metadata filtering, ANN (HNSW) basics, IR metrics, ACL/tenant filtering.
- **High-ROI:** domain fine-tuning of embeddings, ColBERT for hard domains, quantization for scale.
- **Optional / situational:** SPLADE, binary/Matryoshka embeddings, custom fusion weighting — adopt with eval evidence and at scale.

---

### Capstone project for this module
On a fixed eval set, produce a table comparing **BM25-only vs. dense-only vs. hybrid(RRF) vs. hybrid+rerank** on recall@k and nDCG, plus p95 latency for each. Then add a strict tenant/ACL filter and prove (with an adversarial test) that no cross-tenant document is ever retrievable. This is the exact exercise that demonstrates production-grade retrieval competence in interviews.
