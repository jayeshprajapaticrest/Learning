# Module 6 — Graph-RAG

> Powerful for **global, connect-the-dots, and multi-hop** questions that vector search alone answers poorly — but operationally heavy. Learn the concepts thoroughly; deploy only when your data *and* your question types justify the complexity. This is intentionally the **last** module to deploy, not the first.

---

## 1. Why it matters

Standard (vector) RAG retrieves **locally similar chunks**. It struggles with two question classes:

1. **Multi-hop / relational** — "Which products made by suppliers in region X were recalled after 2022?" The answer requires *traversing relationships*, not finding one similar passage.
2. **Global / holistic** — "What are the main themes across these 10,000 incident reports?" No single chunk contains the answer; it requires *aggregating across the whole corpus*.

Graph-RAG builds a **knowledge graph** (entities as nodes, relationships as edges) from your corpus and retrieves by **traversing structure** and/or by reading pre-computed **community summaries**. This captures relationships and global structure that flat vector search loses. Primary, field-defining source: **Microsoft "From Local to Global: A Graph RAG Approach to Query-Focused Summarization"** (Edge et al., 2024, arXiv:2404.16130).

---

## 2. Core concepts

### Knowledge graph construction
- **Extraction:** an LLM (or NLP pipeline) reads chunks and emits **entities** + **relationships** (+ descriptions/claims). This is the expensive part — an LLM pass over the whole corpus.
- **Graph store:** Neo4j (Cypher), Memgraph, Amazon Neptune, or property graphs in some vector DBs. Nodes carry properties; edges carry typed relations.
- **Hybrid storage:** keep vector embeddings *on nodes/edges/chunks* too, so you can do semantic entry-point lookup **and** graph traversal.

### Community detection & summarization (the "global" trick)
Microsoft GraphRAG clusters the graph into **communities** (using algorithms like **Leiden**), then has the LLM write a **summary for each community** at multiple hierarchy levels — offline. At query time:
- **Global search:** map over community summaries → partial answers → reduce into a final answer. Great for "what are the themes" questions.
- **Local search:** start from query-relevant entities → expand to neighbors, relationships, and connected chunks → answer. Great for entity-centric questions.

### Retrieval modes
| Mode | Mechanism | Best for |
|------|-----------|----------|
| **Local search** | Entity lookup → neighborhood expansion | Specific entity questions, multi-hop |
| **Global search** | Map-reduce over community summaries | Corpus-wide themes/summarization |
| **Hybrid / vector+graph** | Semantic entry point, then traverse | Most practical deployments |
| **Text-to-Cypher/SPARQL** | LLM writes a graph query | Precise, structured questions over a clean KG |

### Related approaches
- **RAPTOR** (arXiv:2401.18059) — a *tree* of recursive summaries (cheaper, no explicit entity graph) — often a lighter alternative for "global" questions.
- **HippoRAG** (Gutiérrez et al., 2024, arXiv:2405.14831) — personalized PageRank over a KG, inspired by hippocampal indexing; strong multi-hop with lower cost.
- **LightRAG** (Guo et al., 2024, arXiv:2410.05779) — dual-level (low/high) graph retrieval, cheaper incremental updates than GraphRAG.
- **LazyGraphRAG** (Microsoft, 2024 blog) — defers expensive summarization to query time to cut indexing cost dramatically.

---

## 3. Learning path

### Beginner
- Build a small KG: LLM-extract entities/relations from ~50 docs into Neo4j; explore with Cypher.
- Read the Microsoft GraphRAG paper (2404.16130) and run the official `microsoft/graphrag` package on a sample corpus; try local vs. global search.

### Intermediate
- Implement **hybrid vector+graph retrieval** with LlamaIndex `PropertyGraphIndex` or LangChain + Neo4j (`Neo4jVector`, GraphCypherQAChain).
- Implement **text-to-Cypher** Q&A over a clean graph; handle generation errors/guardrails.

### Advanced
- Implement **community detection + summarization** yourself (Leiden via `igraph`/`graspologic`) and a map-reduce global search.
- Compare **GraphRAG vs. RAPTOR vs. HippoRAG vs. plain hybrid+rerank** on a multi-hop eval set (e.g., HotpotQA-style or your domain). Quantify cost vs. quality.

### Expert
- Design **incremental graph updates** (entity resolution/dedup, edge merging, re-summarizing affected communities) — the hardest operational problem.
- Build entity **resolution/canonicalization** (the same entity referred to many ways) at scale; manage graph schema/ontology governance.

---

## 4. Best resources

- **Papers:** Microsoft GraphRAG (2404.16130); RAPTOR (2401.18059); HippoRAG (2405.14831); LightRAG (2410.05779); plus IRCoT (2212.10509) for multi-hop framing.
- **Docs/blogs:** Microsoft Research GraphRAG blog series & docs (incl. LazyGraphRAG); Neo4j *"GraphRAG"* developer guides and the *Neo4j + LLM* blog (Tomaž Bratanič's posts are excellent and accurate); LlamaIndex `PropertyGraphIndex` docs; LangChain graph QA docs.
- **Repos:** `microsoft/graphrag`, `HKUDS/LightRAG`, `OSU-NLP-Group/HippoRAG`, `neo4j/neo4j-graphrag-python`, `run-llama/llama_index` (property graph).
- **Talks:** Microsoft Research GraphRAG talks; Neo4j NODES conference sessions on GraphRAG.

---

## 5. Production architecture patterns

- **Hybrid retrieval:** vector search to find entry-point entities/chunks, then graph traversal for relationships — rather than pure-graph.
- **Offline summarization, online assembly:** precompute community summaries; keep query-time map-reduce bounded.
- **Separate stores, joined by IDs:** vector DB for chunks/embeddings + graph DB for structure, linked by stable entity/chunk IDs.
- **Schema/ontology layer:** define allowed entity/relation types to keep extraction consistent and queryable.
- **Cost gating:** route only the questions that need it (global/multi-hop) to GraphRAG; everything else uses cheaper hybrid RAG.

---

## 6. Common mistakes & anti-patterns

- **Reaching for GraphRAG before hybrid + rerank + eval.** It's often not the bottleneck and adds large cost/latency/ops.
- **Underestimating indexing cost** — full-corpus LLM extraction + summarization is expensive and slow; budget it (consider LazyGraphRAG/LightRAG for cost).
- **No entity resolution** → duplicate/fragmented nodes → broken traversal.
- **Letting the LLM extract an unconstrained schema** → noisy, unqueryable graph. Constrain types.
- **Ignoring incremental updates** → the graph rots; re-building from scratch each change is infeasible at scale.
- **Using GraphRAG for simple lookup questions** where plain vector RAG is faster and just as good.
- **Trusting generated Cypher/SPARQL without validation/guardrails.**

---

## 7. Interview-level expectations

- Explain *which* question types GraphRAG beats vector RAG on (global/thematic, multi-hop/relational) and why.
- Describe Microsoft GraphRAG: extraction → graph → community detection (Leiden) → summaries → local vs. global search (map-reduce).
- Contrast GraphRAG vs. RAPTOR vs. HippoRAG vs. hybrid+rerank on cost/quality.
- Discuss the operational hard parts: extraction cost, entity resolution, incremental updates, schema governance.
- Give a clear "when NOT to use GraphRAG" answer (signals seniority).

---

## 8. Enterprise-scale considerations

- **Indexing cost & time** dominate; model $ per million docs, and prefer incremental-friendly variants (LightRAG/Lazy) at scale.
- **Entity resolution at scale** is a genuine data-engineering project (blocking, similarity, canonical IDs).
- **Graph DB ops:** sizing, traversal performance, HA, backups — a new operational surface for most teams.
- **Access control on a graph** is harder than on chunks (relationships can leak info); enforce ACLs on traversal.
- **Governance:** ontology/schema ownership, drift, and auditability of extracted facts.

---

## 9. Trade-offs & decision framework

```
Are questions mostly local lookup ("what does the doc say about X")?
   → Plain hybrid RAG + rerank. Do NOT build a graph.

Are questions multi-hop/relational ("connect A→B→C")?
   → GraphRAG local search, HippoRAG, or iterative retrieval (Module 5).

Are questions global/thematic ("summarize themes across the corpus")?
   → GraphRAG global search or RAPTOR.

Cost-sensitive indexing / frequent updates?
   → LightRAG / LazyGraphRAG / RAPTOR over full Microsoft GraphRAG.

Clean, structured domain with a real ontology?
   → Knowledge graph + text-to-Cypher/SPARQL.

Always: prove the lift on a multi-hop/global eval set before committing.
```

---

## 10. Real-world use cases

- **Microsoft GraphRAG** — query-focused summarization over large private corpora (the originating use case).
- **Fraud / AML / security investigations** — relationship traversal across entities/transactions.
- **Healthcare & life sciences** — drug–gene–disease relationship reasoning over literature.
- **Enterprise knowledge graphs** — connecting people, projects, systems, and documents for org-wide Q&A.
- **Customer 360 / supply chain** — multi-hop questions over interconnected records.

---

## 11. Essential vs optional

- **Essential (conceptual):** understand when graph structure beats vector similarity; know the Microsoft GraphRAG pipeline; know the lighter alternatives.
- **Optional / situational (deployment):** building/operating a production GraphRAG system — only when multi-hop/global questions and relational data justify the cost. For many enterprises, RAPTOR or hybrid+rerank is the better ROI.

---

### Capstone project for this module
Take a corpus with genuine relational/multi-hop questions. Build (a) hybrid RAG + rerank and (b) GraphRAG (Microsoft package or LlamaIndex PropertyGraphIndex). Evaluate both on multi-hop and global questions for answer correctness, *and* report indexing cost/time and per-query latency. Write the decision: when is the graph worth it for this data?
