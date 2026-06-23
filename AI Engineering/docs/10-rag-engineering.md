# 10 — RAG Engineering Deep Dive

> Builds on [T01](01-rag-pipelines.md). Here we go deeper on the engineering techniques
> that separate a good retriever from a great one: **component-aware chunking**, **hybrid
> (BM25 + dense)** with proper fusion, **reranking** trade-offs, **Graph-RAG basics**, and
> **query rewriting + multi-hop retrieval** for questions one search can't answer.

---

## 1. Component-aware (smart) chunking

T01 introduced chunking strategies. **Component-aware chunking** is the production
endpoint: split a document along its *semantic components* — title, section, paragraph,
list, table, code block, figure — instead of along arbitrary character windows. Each
chunk is a coherent unit a human would recognize.

### 1.1 Why component boundaries beat character windows

A 512-token window cuts a table in half, orphans a list from its heading, and splices the
end of one section onto the start of the next. The embedding of such a chunk is a blur of
two topics → poor retrieval. Component boundaries keep each chunk **about one thing**.

```
 character window:                    component-aware:
 ┌─────────────────────────┐          ┌──────────────────────┐  Title + intro
 │ ...end of §2. §3 Refunds│          ├──────────────────────┤  §3 Refunds (whole)
 │ A refund may be issued  │   vs     ├──────────────────────┤  Table: refund SLAs (whole)
 │ within 30 | days. Table:│          ├──────────────────────┤  §4 Exceptions (whole)
 │ Region SLA ──────...    │          └──────────────────────┘
 └─────────────────────────┘          each chunk = one coherent component
```

### 1.2 The pipeline: parse → elements → group → enrich

Component-aware chunking **depends on a structure-aware parser** (Docling/Unstructured,
[T02](02-document-ingestion.md)) that emits typed elements. You then group elements into
chunks with type-specific rules.

```python
from unstructured.partition.auto import partition
from unstructured.documents.elements import Title, Table, ListItem, NarrativeText

elements = partition(filename="policy.pdf", strategy="hi_res", infer_table_structure=True)

def component_chunk(elements, max_tokens=512):
    chunks, buf, buf_tokens, heading_path = [], [], 0, []
    def flush():
        nonlocal buf, buf_tokens
        if buf:
            chunks.append({"text": "\n\n".join(e.text for e in buf),
                           "section_path": " / ".join(heading_path),
                           "types": [type(e).__name__ for e in buf]})
            buf, buf_tokens = [], 0
    for el in elements:
        if isinstance(el, Title):                 # heading → new section boundary
            flush(); heading_path = heading_path[:el.metadata.category_depth] + [el.text]
        if isinstance(el, Table):                 # tables are ATOMIC — never split
            flush(); chunks.append({"text": el.metadata.text_as_html,
                                    "section_path": " / ".join(heading_path), "types": ["Table"]})
            continue
        t = tok_len(el.text)
        if buf_tokens + t > max_tokens:           # overflow → flush, start fresh chunk
            flush()
        buf.append(el); buf_tokens += t
    flush()
    return chunks
```

### 1.3 Type-specific handling rules

| Component | Rule |
|-----------|------|
| **Title/heading** | starts a new chunk; record full heading path in metadata |
| **Table** | keep atomic; store as HTML/Markdown; embed a generated summary, return the full table (small-to-big, T01 §2.5) |
| **List** | keep the list with its introducing sentence; don't split items across chunks |
| **Code block** | atomic; never split mid-block |
| **Figure/image** | embed a VLM caption; store image URI in metadata |
| **Long paragraph run** | sub-split with recursive splitter + overlap, preserving section path |

### 1.4 Enrichment that compounds the gains

- **Heading-path prefix** — prepend `"Refunds / Regional SLAs"` to the chunk text before
  embedding so the section context is in the vector.
- **Contextual retrieval** (T01 §2.5) — LLM-generated 1–2 line situating summary.
- **Late chunking** — embed the whole document with a long-context embedder, then mean-pool
  token embeddings per component, so each chunk's vector "remembers" the surrounding
  document. Strong when components are short and context-dependent.

**Net effect:** component-aware chunking + heading prefix + atomic tables is usually the
single biggest retrieval-quality upgrade after "go hybrid + rerank."

---

## 2. Hybrid retrieval (BM25 + dense), done right

T01 §3 introduced hybrid + RRF. Engineering details that matter in production:

### 2.1 The two failure modes you're fixing

- **Dense-only** misses exact tokens: SKUs, error codes, function names, rare acronyms,
  legal section numbers. Embeddings smooth over the exact string.
- **Sparse-only (BM25)** misses paraphrase and synonymy: "PTO" vs "paid time off",
  "terminate" vs "cancel".

Hybrid covers both. On mixed enterprise traffic it reliably beats either alone.

### 2.2 Fusion: RRF vs weighted score normalization

```python
# RRF (rank-based) — robust default; no score-scale tuning needed
def rrf(lists, k=60):
    scores = {}
    for results in lists:
        for rank, doc_id in enumerate(results):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)

# Weighted normalization — when you want to bias toward one signal; must normalize scales
def weighted_fuse(dense, sparse, alpha=0.6):       # alpha = dense weight
    d = minmax({i: s for i, s in dense})
    s = minmax({i: s for i, s in sparse})
    keys = set(d) | set(s)
    return sorted(keys, key=lambda i: alpha*d.get(i,0) + (1-alpha)*s.get(i,0), reverse=True)
```

Guidance: **start with RRF** (no tuning, scale-robust). Move to weighted `alpha` only if
you have an eval set to tune it and a reason to bias (e.g. code search → favor sparse).

### 2.3 Learned sparse (SPLADE / BM42) — the modern middle ground

Classic BM25 matches exact tokens. **Learned sparse** models (SPLADE, Qdrant's BM42)
produce sparse vectors that include *term expansions* — they fire on related terms too,
narrowing the gap with dense while keeping sparse's exactness and interpretability. Many
engines run dense + learned-sparse and fuse server-side (T03 §3.4).

### 2.4 Engineering checklist

- Push BM25/sparse into the engine (OpenSearch/Qdrant/Weaviate), don't fuse in Python at scale.
- Fuse a generous candidate pool (≈50 each) *before* reranking — recall first, precision later.
- Tokenize/analyze the sparse side to match your domain (custom analyzers for codes/IDs).
- Apply tenant + ACL filters to **both** legs (T03/T09).

---

## 3. Reranking — the precision stage

T01 §4 covered the mechanics. Engineering trade-offs:

| Reranker | Latency | Quality | Privacy | Notes |
|----------|---------|---------|---------|-------|
| **Cohere Rerank 3.5** (hosted) | low | high | data leaves network | easiest, multilingual |
| **`bge-reranker-v2-m3`** (local cross-encoder) | medium (GPU helps) | high | on-prem | strong open default |
| **Voyage rerank** (hosted) | low | high | hosted | pairs with Voyage embeddings |
| **LLM-as-reranker** | high | very high | depends | use only for tiny candidate sets / hard cases |

Production patterns:
- **Two-stage funnel:** retrieve 50–100 (cheap, high recall) → rerank to 5–10 (precise).
- **Relevance floor:** drop everything below a tuned threshold → enables a clean "I don't
  know" path (the top hallucination guard, [T06](06-guardrails-evals.md)).
- **Batch + cache** rerank scores for repeated (query, chunk) pairs.
- **Budget-aware:** if you have a <100 ms p95 budget and can't fit a cross-encoder, lean
  on better first-stage hybrid + learned-sparse instead.

---

## 4. Graph-RAG basics

T05 covered the full knowledge-layer. Here's the **minimal Graph-RAG** you can add to an
existing vector RAG to answer relational and "global" questions.

### 4.1 When flat RAG fails

Flat RAG retrieves the top-k *most similar passages*. It struggles with:
- **Multi-entity relational questions** — "which suppliers are linked to the delayed
  shipments in the EU?" (needs to join supplier↔shipment↔region).
- **Global/aggregative questions** — "what are the recurring themes across all incident
  reports?" (the answer isn't in any single chunk).

Graph-RAG adds an explicit structure of entities and relationships so the retriever can
*traverse* instead of only *match*.

### 4.2 The lightweight build

```python
# 1. Extract entities + relations per chunk (constrained to a small schema) — see T05 §3
triples = extract_triples(chunk_text)          # (subject, relation, object)
# 2. Store edges with back-links to the chunk they came from
for s, r, o in triples:
    graph.add_edge(s, o, relation=r, chunk_id=chunk["id"], tenant_id=tenant)
# 3. Also index chunks in the vector store as usual (T03)
```

### 4.3 Two query strategies

**(a) Local Graph-RAG (entity-anchored).** Find entities in the question → pull their
graph neighborhood → restrict vector retrieval to the linked chunks.

```python
def local_graph_rag(question, tenant):
    seeds = link_entities(question)                       # "EU", "delayed shipments"
    nbhd = graph.neighborhood(seeds, hops=2, tenant_id=tenant)
    doc_ids = {n.chunk_id for n in nbhd.nodes if n.chunk_id}
    chunks = hybrid_retrieve(question, filters={"tenant_id": tenant, "chunk_id": {"in": doc_ids}})
    return generate(question, graph_facts=nbhd.edges, chunks=chunks)
```

**(b) Global Graph-RAG (community summaries).** Cluster the graph into communities
(e.g. Leiden), pre-summarize each community offline, then answer global questions by
map-reducing over relevant community summaries. This is the core idea behind Microsoft's
GraphRAG for "query-focused summarization" over a whole corpus.

```
 corpus → graph → detect communities → summarize each (offline)
 question → pick relevant communities → summarize-each-answer → reduce → final answer
```

### 4.4 Routing: don't graph everything

Graph-RAG costs more (extraction + traversal). **Route by question type:**
lookup/factoid → flat RAG; relational/multi-entity → local Graph-RAG; global/thematic →
community summaries. A cheap classifier (Haiku) picks the path.

---

## 5. Query rewriting & multi-hop retrieval

T01 §5 covered single-shot rewriting (standalone, multi-query, HyDE). **Multi-hop** is for
questions whose answer requires chaining facts retrieved in *separate* steps — one
retrieval's result becomes the next retrieval's query.

### 5.1 What needs multiple hops

> "Who is the manager of the engineer who fixed incident #4021?"

No single chunk has this. You must: (1) find who fixed #4021 → "Dana"; (2) find Dana's
manager → "Sam". Two dependent retrievals. Single-shot RAG retrieves passages about #4021
and guesses — often wrong.

```
 Q ──► hop 1: "who fixed #4021?" ──► "Dana" ──► hop 2: "who manages Dana?" ──► "Sam" ──► answer
        (retrieve)                              (retrieve, using hop-1 result)
```

### 5.2 Decomposition (plan the hops up front)

```python
DECOMPOSE = """Break the question into an ordered list of sub-questions where each may
depend on earlier answers. Use {{ANSWER_n}} to reference a prior sub-answer.
Return JSON list. Question: {q}"""

# → ["Who fixed incident #4021?", "Who is the manager of {{ANSWER_1}}?"]
def multihop(question):
    subqs = json.loads(llm.invoke(DECOMPOSE.format(q=question)).content)
    answers = []
    for sq in subqs:
        for i, a in enumerate(answers):                  # substitute prior answers
            sq = sq.replace(f"{{{{ANSWER_{i+1}}}}}", a)
        ctx = hybrid_retrieve(sq)
        answers.append(generate(sq, ctx))
    return generate(question, context=list(zip(subqs, answers)))   # final synthesis
```

### 5.3 Iterative / self-ask retrieval (decide hops dynamically)

When you don't know the hop count in advance, let the model **iteratively ask follow-up
queries** until it has enough — retrieve, reflect ("what's still missing?"), retrieve
again. This is essentially a small retrieval **agent** ([T04](04-langgraph-agents.md)):

```python
def iterative_retrieve(question, max_hops=4):
    known, hops = [], 0
    while hops < max_hops:
        gap = llm.invoke(f"Question: {question}\nKnown:\n{known}\n"
                         "What single fact is still missing? Reply 'DONE' if none, "
                         "else give a search query.").content
        if gap.strip() == "DONE":
            break
        known.append({"q": gap, "ctx": hybrid_retrieve(gap)})
        hops += 1
    return generate(question, context=known)
```

This is the bridge to **agentic RAG**: retrieval as a tool the agent calls repeatedly,
with reflection between calls. Patterns like *self-RAG* (the model decides when to
retrieve and grades the relevance of what it got) and *corrective RAG* (if retrieval is
weak, fall back to web/another source) build on this loop.

### 5.4 Cost & failure control for multi-hop

- **Cap hops** — runaway multi-hop is expensive and drifts off-topic.
- **Verify each hop's grounding** before using it as input to the next (errors compound).
- **Use a fast model** for decomposition/reflection, a strong one for final synthesis.
- **Fall back to flat RAG** for simple questions — route, don't multi-hop everything.

---

## 6. Putting the engineering together

```python
def advanced_rag(question, tenant):
    route = classify(question)                            # factoid | relational | global | multihop
    if route == "multihop":
        return iterative_retrieve(question)
    if route in ("relational", "global"):
        return local_graph_rag(question, tenant)          # or community summaries for global
    # default: component-chunked hybrid + rerank + floor (T01/T10)
    cands = hybrid_retrieve(rewrite(question), filters={"tenant_id": tenant}, top_k=50)
    kept  = [c for c, s in rerank(question, cands) if s >= 0.2]
    return generate(question, kept) if kept else "I don't have that information."
```

## 7. Checklist

- [ ] Chunk on components (parser-driven), atomic tables/lists/code, heading-path prefix.
- [ ] Hybrid (dense + BM25/learned-sparse), RRF by default, filters on both legs.
- [ ] Funnel: 50–100 candidates → rerank to 5–10 → relevance floor → "I don't know" path.
- [ ] Add lightweight Graph-RAG for relational/global questions; route by question type.
- [ ] Multi-hop via decomposition (known hops) or iterative self-ask (dynamic), with hop caps.
- [ ] Verify grounding between hops; cheap model for planning, strong model for synthesis.

**Next:** [11 — LangGraph Complete Feature Reference](11-langgraph-features.md).
