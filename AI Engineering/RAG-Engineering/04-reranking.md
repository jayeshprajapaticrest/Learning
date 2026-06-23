# Module 4 — Reranking

> The highest precision-per-dollar upgrade in RAG once basic retrieval works. First-stage retrieval optimizes **recall** (don't miss the right doc); reranking optimizes **precision** (put the right doc at the top). You need both.

---

## 1. Why it matters

First-stage retrievers (BM25, bi-encoder dense) are fast but *coarse* — they compress a passage into one vector or a bag of words, so the top-k is noisy. The LLM then suffers from:

- **"Lost in the middle"** (Liu et al., 2023, arXiv:2307.03172) — models use info at the *start/end* of context far better than the middle, so ranking order materially changes answer quality.
- **Context dilution / distraction** — irrelevant passages in the prompt actively *degrade* answers and waste tokens.

A **reranker** is a more expensive, more accurate model that re-scores a *small* candidate set (e.g., top 50–100 → top 5). Because it only runs on candidates, you get cross-encoder-level accuracy at acceptable cost. Empirically (Anthropic Contextual Retrieval; Wang et al. 2024, arXiv:2407.01219) adding a reranker is one of the most reliable quality boosts available.

---

## 2. Core concepts

### Two-stage retrieval (retrieve → rerank)
```
Query → first-stage retriever (recall-oriented, top 50–200)
      → reranker (precision-oriented, cross-encoder/late-interaction)
      → top 3–10 → context assembly
```

### Reranker types
| Type | How it works | Accuracy | Cost/latency |
|------|--------------|----------|--------------|
| **Cross-encoder** | Concatenate (query, passage), one transformer pass → relevance score. Sees full interaction. | High | High (one forward pass per candidate) |
| **Late interaction (ColBERT)** | Token-level multi-vector MaxSim. Precompute doc token vectors. | High | Medium; can index for retrieval too |
| **LLM-as-reranker** | Prompt an LLM to score/order passages (pointwise, pairwise, or listwise — e.g., RankGPT) | Very high; flexible | Highest; latency/cost-heavy |
| **Hosted rerank APIs** | Cohere Rerank, Jina, Voyage rerank — managed cross-encoders | High | Low ops, per-call cost |
| **Open cross-encoders** | `BAAI/bge-reranker-v2-*`, `mixedbread`/`mxbai-rerank`, `cross-encoder/ms-marco-*` | High | Self-hosted GPU |

Key primary sources: **monoBERT/cross-encoder reranking** (Nogueira & Cho, "Passage Re-ranking with BERT", arXiv:1901.04085); **RankGPT** listwise LLM reranking (Sun et al., 2023, arXiv:2304.09542); ColBERT (arXiv:2004.12832).

### Pointwise vs. pairwise vs. listwise
- **Pointwise:** score each passage independently (most cross-encoders). Simple, parallel.
- **Pairwise:** compare passages two at a time.
- **Listwise:** rank the whole list at once (RankGPT, RankZephyr) — strongest, costlier.

### How many to retrieve / keep
Typical: retrieve **top 50–150**, rerank, keep **top 3–8**. Tune `k_retrieve` and `k_keep` on your eval set — more candidates → better recall into the reranker but more cost/latency.

---

## 3. Learning path

### Beginner
- Add a cross-encoder reranker (`sentence-transformers` `CrossEncoder` with `ms-marco-MiniLM` or `bge-reranker-base`) on top of your hybrid retriever; measure nDCG/precision lift on your eval set.
- Read Nogueira & Cho (monoBERT) and the "Lost in the Middle" paper.

### Intermediate
- Compare hosted (Cohere Rerank) vs. open (`bge-reranker-v2-m3`) on quality, latency, cost.
- Tune `k_retrieve` / `k_keep`; quantify the recall→precision trade-off.

### Advanced
- Implement **ColBERT** late interaction (retrieve + rerank) for a hard domain.
- Implement an **LLM listwise reranker** (RankGPT-style) and measure where it beats cross-encoders (and where its latency isn't worth it).
- **Fine-tune a cross-encoder** on in-domain (query, passage, label) triples with hard negatives.

### Expert
- Build a **two-tier reranking** path (cheap cross-encoder → optional LLM rerank for hard queries via the router).
- Distill an LLM reranker into a small cross-encoder for production latency.
- Optimize serving: batch candidates, quantize the reranker, GPU autoscaling, and cache rerank scores for repeated (query, doc) pairs.

---

## 4. Best resources

- **Papers:** monoBERT (1901.04085); RankGPT (2304.09542); RankZephyr (Pradeep et al., 2023, arXiv:2312.02724); ColBERT/v2 (2004.12832 / 2112.01488); Lost in the Middle (2307.03172).
- **Docs/blogs:** Cohere Rerank docs & blog; Jina/Voyage reranker docs; `sentence-transformers` Cross-Encoder docs; Pinecone *"Rerankers and Two-Stage Retrieval"* guide; Anthropic Contextual Retrieval (shows rerank lift).
- **Repos:** `UKPLab/sentence-transformers`, `FlagOpen/FlagEmbedding` (BGE rerankers), `castorini/rank_llm` (RankGPT/RankZephyr), `AnswerDotAI/rerankers` (unified reranker API across backends — great for experimentation).
- **Benchmarks:** BEIR (zero-shot), MTEB reranking tasks.

---

## 5. Production architecture patterns

- **Retrieve-then-rerank** as the default serving shape.
- **Candidate cap** (e.g., 100) to bound reranker cost; batch the cross-encoder forward passes.
- **Reranker behind its own service/endpoint** (GPU) with autoscaling, or a hosted API for low ops.
- **Score caching** for hot (query, doc) pairs; semantic cache at the query level.
- **Router-gated LLM reranking:** only escalate to an expensive listwise LLM reranker for queries classified as hard.

---

## 6. Common mistakes & anti-patterns

- **Skipping reranking** and feeding raw top-k to the LLM (precision suffers, "lost in the middle" bites).
- **Reranking too many candidates** → latency/cost blowup with diminishing returns.
- **Reranking too few** → the right doc never enters the reranker (recall bottleneck upstream).
- **Using a reranker as the first-stage retriever** (cross-encoders can't scan millions of docs — O(N) forward passes).
- **Not measuring the lift** — adding a reranker without eval proof it helps your data.
- **Ignoring max sequence length** — cross-encoders truncate long passages; chunk accordingly.
- **Forgetting to put the best passage where the model reads best** (start/end) after reranking — see Module 7.

---

## 7. Interview-level expectations

- Explain why retrieval is two-stage: recall (cheap, broad) then precision (expensive, narrow).
- Contrast bi-encoder vs. cross-encoder vs. ColBERT and why cross-encoders can't be the retriever.
- Explain pointwise/pairwise/listwise reranking and the cost/quality ladder.
- Explain how reranking interacts with "lost in the middle" and context ordering.
- Reason about `k_retrieve`/`k_keep` and latency budgets.

---

## 8. Enterprise-scale considerations

- **Latency budget:** reranking adds a hop; cross-encoder over 100 candidates on GPU is typically tens of ms batched — measure and SLO it. LLM rerankers can add seconds; gate them.
- **Cost:** hosted rerank is per-call; self-hosted is GPU capacity. Model the crossover.
- **Throughput:** batch aggressively; quantize (INT8) the reranker.
- **Domain drift:** periodically re-evaluate the reranker; fine-tune on production-labeled data (from observability traces).

---

## 9. Trade-offs & decision framework

```
Just need a reliable boost, low ops?        → Hosted rerank API (Cohere/Voyage/Jina).
Self-host / data can't leave / cost at scale? → bge-reranker-v2 / mxbai cross-encoder on GPU.
Hard domain, want retrieval+rerank unified?  → ColBERTv2.
Highest accuracy, latency-tolerant, hard queries only → LLM listwise rerank (router-gated).

How many candidates? Start k_retrieve≈50–100, k_keep≈5; tune on eval.
```

---

## 10. Real-world use cases

- **Enterprise Q&A / support** — rerank to surface the one authoritative passage among many near-duplicates.
- **Search relevance** (e-commerce, web) — classic two-stage IR; rerankers are standard.
- **RAG over large heterogeneous corpora** where first-stage recall is high but precision is low.
- **Anthropic's Contextual Retrieval** explicitly combines contextual embeddings + BM25 + reranking for best results.

---

## 11. Essential vs optional

- **Essential:** a cross-encoder reranker in a two-stage pipeline; tuning `k_retrieve`/`k_keep`; measuring lift.
- **High-ROI:** hosted rerank for fast wins; ColBERT for hard domains.
- **Optional / situational:** LLM listwise reranking, reranker fine-tuning/distillation — at scale or for hard queries, with eval evidence.

---

### Capstone project for this module
Take your hybrid retriever and add three rerankers (open cross-encoder, hosted API, and an LLM listwise reranker). Produce a quality (nDCG@10, answer faithfulness) vs. p95-latency vs. cost-per-query chart, sweep `k_retrieve`, and write a recommendation on which reranker to ship and why.
