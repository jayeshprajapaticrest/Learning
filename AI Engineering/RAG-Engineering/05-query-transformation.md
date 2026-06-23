# Module 5 — Query Transformation (Rewriting, Multi-Query, Multi-Hop)

> Users ask bad queries: terse, ambiguous, conversational, or compound. The query you receive is rarely the query you should *search with*. This module is about transforming the user's intent into one-or-more effective retrieval queries — and iterating when one pass isn't enough.

---

## 1. Why it matters

Retrieval quality is bounded by query quality. Common failure modes the raw query causes:

- **Vocabulary mismatch** — user says "how do I reset my password," docs say "credential recovery procedure." Embeddings help but don't fully solve this.
- **Conversational context loss** — "what about the second one?" is meaningless without rewriting against chat history.
- **Compound / multi-faceted questions** — "compare the security and pricing of A vs B" needs *multiple* retrievals.
- **Multi-hop questions** — "who is the CEO of the company that acquired X?" requires retrieving X's acquirer, *then* that company's CEO. A single retrieval cannot answer it.

Query transformation techniques fix these and are some of the biggest wins on *hard* and *conversational* queries.

---

## 2. The techniques (toolbox)

### Query rewriting / normalization
Use an LLM (or rules) to clean, expand, and disambiguate: spelling, acronym expansion, adding synonyms, and **history-aware rewriting** (condense the conversation + latest turn into one standalone query). Primary source: **"Query Rewriting for Retrieval-Augmented LLMs"** (Ma et al., 2023, arXiv:2305.14283). History-aware rewriting is essential for any chat RAG (LangChain `create_history_aware_retriever`).

### HyDE (Hypothetical Document Embeddings)
Ask the LLM to *write a hypothetical answer* to the query, then embed **that** (not the query) for dense retrieval — a fake answer lives closer in embedding space to real answers than the question does. Primary source: **Gao et al., 2022, arXiv:2212.10496**. Cheap, often effective for zero-shot domains; can hurt when the LLM hallucinates off-topic — A/B it.

### Multi-query (query expansion / fan-out)
Generate N paraphrases/sub-queries from the original, retrieve for each, then **fuse** (union + dedup, or RRF). Improves recall by covering multiple phrasings/facets. (LangChain `MultiQueryRetriever`.) Pairs naturally with RRF from Module 3.

### Query decomposition
Break a compound question into independent sub-questions, retrieve+answer each, then synthesize. (LlamaIndex `SubQuestionQueryEngine`.) Best for "compare/and/multi-part" questions.

### Step-back prompting
Generate a more *general* question to retrieve broad principles/context, alongside the specific query. Primary source: **"Take a Step Back"** (Zheng et al., 2023, arXiv:2310.06117). Helps reasoning-heavy questions.

### Multi-hop / iterative retrieval
For questions requiring chained facts, retrieve → read → form the *next* query from what you learned → retrieve again, until you can answer. This is **agentic/iterative RAG**. Primary sources: **Self-Ask** (Press et al., 2022, arXiv:2210.03350); **IRCoT — Interleaving Retrieval with Chain-of-Thought** (Trivedi et al., 2022, arXiv:2212.10509); **FLARE** active retrieval (Jiang et al., 2023, arXiv:2305.06983); **DSP / Demonstrate-Search-Predict** (Khattab et al., 2022, arXiv:2212.14024). GraphRAG (Module 6) is another answer to multi-hop.

### Routing
Classify the query to pick the right index/tool/path (e.g., docs vs. SQL vs. web). Often paired with transformation. (LlamaIndex `RouterQueryEngine`; LangChain routing.)

---

## 3. Learning path

### Beginner
- Implement **history-aware query rewriting** for a chat RAG and observe the difference on follow-up questions.
- Implement **HyDE** and **multi-query + RRF**; measure recall lift on hard queries.

### Intermediate
- Implement **query decomposition** for compound questions and **routing** across 2+ sources.
- Read Ma et al. (rewriting), Gao (HyDE), Zheng (step-back).

### Advanced
- Implement an **iterative multi-hop** loop (Self-Ask / IRCoT style): generate follow-up queries from intermediate findings; add a stop condition and a max-hop budget.
- Use **DSPy** to *optimize* the rewrite/decompose prompts against your metric instead of hand-crafting them.

### Expert
- Build a **router + transformer policy**: cheap path for simple queries, decomposition/multi-hop for complex ones, with cost/latency budgets and loop guards.
- Train/distill a small query-rewriter model from LLM outputs for latency.

---

## 4. Best resources

- **Papers:** Query Rewriting (2305.14283); HyDE (2212.10496); Step-Back (2310.06117); Self-Ask (2210.03350); IRCoT (2212.10509); FLARE (2305.06983); DSP (2212.14024).
- **Docs/blogs:** LangChain *query transformation* / `MultiQueryRetriever` / history-aware retriever docs and the `rag-from-scratch` notebooks (excellent, technique-by-technique); LlamaIndex query-transformations, `SubQuestionQueryEngine`, `RouterQueryEngine` docs; DSPy docs & tutorials.
- **Repos:** `langchain-ai/rag-from-scratch`, `stanfordnlp/dspy`, `stanfordnlp/dsp`, `run-llama/llama_index`.

---

## 5. Production architecture patterns

- **Rewrite-then-retrieve** as the default for chat RAG (always condense history first).
- **Fan-out/fan-in** for multi-query: parallel retrievals → RRF/dedup → rerank.
- **Bounded iterative loop** for multi-hop: max hops, per-hop timeout, and a confidence/stop check to avoid runaway cost.
- **Router-first**: classify cheaply (heuristic or small model) before spending on transformation.
- **Cache** rewritten queries and sub-query results.

---

## 6. Common mistakes & anti-patterns

- **No history-aware rewriting in chat** → follow-ups retrieve garbage.
- **Applying every technique to every query** → latency/cost explosion; gate by query type.
- **Unbounded multi-hop loops** → cost blowups and oscillation; always cap hops and add a stop condition.
- **HyDE on factual/keyword queries** where a hallucinated hypothetical drags retrieval off-topic — measure, don't assume.
- **Multi-query without dedup/fusion** → redundant, contradictory context.
- **Adding an LLM rewrite step that adds latency without measured recall gain.**

---

## 7. Interview-level expectations

- Explain why the raw user query is often the wrong search query, with examples.
- Explain HyDE and *why* embedding a hypothetical answer can beat embedding the question.
- Explain multi-query + RRF and query decomposition; when to use each.
- Explain multi-hop/iterative retrieval (Self-Ask/IRCoT) and the latency/cost/loop-control trade-offs.
- Explain history-aware rewriting for conversational RAG.

---

## 8. Enterprise-scale considerations

- **Latency/cost:** each LLM transformation is an extra round-trip; budget them and gate via routing.
- **Determinism/caching:** cache rewrites; consider a fine-tuned small rewriter to remove a large-LLM hop.
- **Observability:** log the rewritten/sub-queries and which retrievals fed the answer (crucial for debugging "why did it answer that?").
- **Guardrails:** transformed queries are still attacker-influenced; don't let injected text in history hijack the rewrite.

---

## 9. Trade-offs & decision framework

```
Conversational app?                         → history-aware rewriting (always).
Vocabulary mismatch / zero-shot domain?     → HyDE and/or multi-query.
Low recall, multiple phrasings/facets?      → multi-query + RRF.
Compound "compare/and" question?            → decomposition (sub-questions).
Reasoning needs broad context?              → step-back.
Answer needs chained facts (multi-hop)?     → iterative retrieval / Self-Ask / IRCoT / GraphRAG.
Multiple sources/tools?                      → routing.

Cost control: route simple queries to a single plain retrieval; reserve transforms for hard queries.
```

---

## 10. Real-world use cases

- **Conversational assistants** — history-aware rewriting is table stakes.
- **Research / analyst copilots** — decomposition + multi-hop for "synthesize across these entities."
- **Customer support** — multi-query to bridge user language vs. KB language.
- **Answer engines (Perplexity-style)** — query rewriting + fan-out + multi-step retrieval.

---

## 11. Essential vs optional

- **Essential:** history-aware rewriting (for chat); multi-query + RRF; query decomposition.
- **High-ROI:** HyDE (where it measures well); routing.
- **Optional / situational:** step-back, full agentic multi-hop, DSPy-compiled query policies — for complex/reasoning workloads, gated by cost.

---

### Capstone project for this module
Build a query-transformation router: classify incoming queries (simple / conversational / compound / multi-hop) and apply the matching technique. Measure recall, answer correctness, latency, and cost **with vs. without** transformation on a query set that deliberately includes follow-ups, compound, and multi-hop questions.
