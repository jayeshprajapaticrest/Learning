# 01 — End-to-End RAG Pipelines

> **Goal:** Build a retrieval pipeline that reliably finds the right context, then
> hands the LLM exactly what it needs to answer faithfully. We cover **smart
> chunking**, **hybrid retrieval**, **reranking**, and **query rewriting** — the four
> levers that move RAG quality the most.

---

## 1. What RAG actually is (and isn't)

RAG = **Retrieval** (find relevant text) + **Augmented Generation** (put it in the
prompt). The LLM answers *from the supplied context* instead of its frozen training
memory. This gives you:

- **Freshness** — answer about data created after the model's cutoff.
- **Attribution** — cite the source passage.
- **Access control** — only retrieve what the user is allowed to see (see [T09](09-security-governance.md)).
- **Smaller models** — a good retriever lets a cheap model answer well.

RAG is **not** a fine-tune. You aren't teaching the model facts; you're feeding facts
at inference time. Reach for fine-tuning only for *behavior/format/tone*, not knowledge.

### The pipeline at a glance

```
                INGEST (offline, T02)                     QUERY (online)
 ┌──────────────────────────────────────┐   ┌────────────────────────────────────────┐
 │ docs → parse → chunk → embed → index  │   │ question                                 │
 └──────────────────────────────────────┘   │    │                                     │
                  │                          │    ▼                                     │
                  ▼                          │  query rewriting / expansion  (§5)        │
         ┌────────────────┐                  │    │                                     │
         │  Vector + BM25 │◄─────────────────┤    ▼                                     │
         │   indexes (T03)│                  │  hybrid retrieval (dense+sparse) (§3)     │
         └────────────────┘                  │    │  top-50 candidates                  │
                                             │    ▼                                     │
                                             │  rerank → top-8 (§4)                      │
                                             │    │                                     │
                                             │    ▼                                     │
                                             │  build prompt → LLM → answer + citations  │
                                             └────────────────────────────────────────┘
```

---

## 2. Smart chunking

**Chunking is the highest-leverage, most-underrated step.** If a chunk is too big it
dilutes the embedding and wastes context; too small and it loses the surrounding
meaning. Bad chunks → bad retrieval → bad answers, no matter how good your model is.

### 2.1 The chunking spectrum

| Strategy | How it splits | Best for | Cost |
|----------|---------------|----------|------|
| **Fixed-size** | every N tokens | quick baseline | trivial |
| **Recursive** | by separators (`\n\n`, `\n`, `. `) with overlap | general prose | trivial |
| **Document-structure** | by headings/sections (Markdown, HTML) | technical docs, wikis | low |
| **Semantic** | split where embedding similarity drops | dense, topic-shifting text | medium (embeds while chunking) |
| **Layout/element** | by parsed elements (title, table, list) | PDFs, reports | high (needs T02 parser) |
| **Late chunking** | embed full doc, then pool per chunk | preserving long-range context | medium |

**Rule of thumb:** start with **recursive, ~512 tokens, 10–15% overlap**, then upgrade
to structure-aware once your parser (T02) emits clean elements.

### 2.2 Recursive chunking (the dependable baseline)

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,            # measured in tokens if you pass a token length fn
    chunk_overlap=64,          # ~12% — keeps a sentence from being cut mid-thought
    separators=["\n\n", "\n", ". ", " ", ""],  # try paragraph → line → sentence → word
    length_function=len,       # swap for a tokenizer-based counter in production
)
chunks = splitter.split_text(document_text)
```

Use a **token** length function, not character count, so chunk sizes match what the
embedding model and LLM actually see:

```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
def tok_len(text: str) -> int:
    return len(enc.encode(text))

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512, chunk_overlap=64, length_function=tok_len,
    separators=["\n\n", "\n", ". ", " ", ""],
)
```

### 2.3 Structure-aware chunking (the upgrade you'll actually ship)

Real enterprise docs have headings, tables, and lists. Splitting on raw characters
shreds them. Split on **document structure** and keep the heading path as metadata —
this single change typically gives the biggest retrieval-quality jump after baseline.

```python
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# Step 1: split on headings, capturing the heading hierarchy as metadata
header_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
    strip_headers=False,
)
sections = header_splitter.split_text(markdown_doc)   # T02 converts PDF/DOCX → markdown

# Step 2: sub-split any section that is still too long
body_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64,
                                               length_function=tok_len)
chunks = body_splitter.split_documents(sections)
# each chunk now carries {"h1": "...", "h2": "...", "h3": "..."}
```

### 2.4 Semantic chunking (when topics drift inside a section)

Split at points where consecutive sentences become dissimilar in embedding space:

```python
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings

semantic = SemanticChunker(
    OpenAIEmbeddings(model="text-embedding-3-large"),
    breakpoint_threshold_type="percentile",  # split at the 95th-percentile distance jump
    breakpoint_threshold_amount=95,
)
chunks = semantic.create_documents([document_text])
```

Cost note: this embeds while chunking, so it's slower/pricier. Reserve it for
high-value corpora (legal, policy) where topic boundaries are subtle.

### 2.5 Context enrichment — the patterns that move the needle

Plain chunks lose the document they came from. Three production patterns fix this:

**(a) Contextual Retrieval (Anthropic's pattern).** Prepend an LLM-generated 1–2
sentence summary that situates each chunk in its document *before* embedding. Reported
to cut retrieval failures substantially. Use a cheap model (Haiku) and **prompt
caching** on the document so you only pay for the document tokens once.

```python
CONTEXT_PROMPT = """Here is a chunk from a document. In 1-2 sentences, situate it
within the overall document so it is searchable on its own. Answer ONLY with the context.

<document>{doc}</document>
<chunk>{chunk}</chunk>"""

def contextualize(doc_text: str, chunk: str, client) -> str:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=128,
        messages=[{"role": "user", "content": CONTEXT_PROMPT.format(doc=doc_text, chunk=chunk)}],
        # cache the big document block across the many chunks of the same doc
    )
    return msg.content[0].text

enriched = f"{contextualize(doc_text, chunk, client)}\n\n{chunk}"
```

**(b) Parent-document / small-to-big.** Embed *small* chunks for precise matching, but
return the *parent* section to the LLM for full context. Best of both worlds.

```python
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore

retriever = ParentDocumentRetriever(
    vectorstore=vectorstore,                 # holds small child chunks
    docstore=InMemoryStore(),                # holds large parent chunks (use Redis/SQL in prod)
    child_splitter=RecursiveCharacterTextSplitter(chunk_size=256),
    parent_splitter=RecursiveCharacterTextSplitter(chunk_size=1500),
)
retriever.add_documents(docs)
```

**(c) Metadata you must always attach** (drives filtering, citations, and access control):

```python
metadata = {
    "doc_id": "policy-2024-0481",
    "source_uri": "sharepoint://hr/policies/leave.pdf",
    "title": "Leave Policy 2024",
    "section_path": "Leave / Parental / Eligibility",
    "page": 7,
    "tenant_id": "acme",          # multi-tenancy — see T05
    "acl": ["group:hr", "group:all-staff"],   # access control — see T09
    "updated_at": "2026-03-01",
    "doc_type": "policy",
}
```

---

## 3. Hybrid retrieval (dense + sparse)

A single retrieval method always has a blind spot:

- **Dense (vector) search** captures *meaning* — "PTO" ≈ "paid time off" — but misses
  exact tokens: product codes, error IDs, acronyms, names.
- **Sparse (keyword/BM25) search** nails exact terms but misses paraphrase.

**Hybrid = run both, then fuse the rankings.** This is the default for serious systems.

### 3.1 Reciprocal Rank Fusion (RRF) — fuse without tuning weights

RRF combines two ranked lists using only positions, so you don't have to normalize
incomparable score scales:

```python
def reciprocal_rank_fusion(result_lists: list[list[str]], k: int = 60) -> list[str]:
    """Each result_list is doc_ids ranked best→worst. Returns fused ranking."""
    scores: dict[str, float] = {}
    for results in result_lists:
        for rank, doc_id in enumerate(results):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)

dense_ids  = vector_search(query, top_k=50)     # from T03
sparse_ids = bm25_search(query, top_k=50)
fused = reciprocal_rank_fusion([dense_ids, sparse_ids])[:50]
```

### 3.2 BM25 sparse retrieval

For a quick local baseline:

```python
from rank_bm25 import BM25Okapi
tokenized = [doc.lower().split() for doc in corpus]
bm25 = BM25Okapi(tokenized)
scores = bm25.get_scores(query.lower().split())
top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:50]
```

In production, push BM25 into the engine: **OpenSearch** does keyword + vector natively,
**Qdrant** supports sparse vectors (e.g. SPLADE/BM42), **Weaviate** has built-in hybrid
with an `alpha` blend. See [T03](03-vector-search.md). Prefer engine-native hybrid over
hand-rolled fusion once you're past prototyping — it's faster and simpler to operate.

### 3.3 When to use which

| Query type | Winner | Why |
|------------|--------|-----|
| "How do I request parental leave?" | dense | paraphrase, semantic |
| "Error E-4021 root cause" | sparse | exact code |
| "Acme MSA section 7.3 indemnity" | hybrid | named entity + concept |
| Most real enterprise traffic | **hybrid** | mix of both |

---

## 4. Reranking

Retrieval optimizes for **recall** (don't miss the right chunk) by pulling ~50
candidates. But the LLM should see only ~5–10, ordered by **precision**. A
**cross-encoder reranker** reads the (query, chunk) pair *together* and scores true
relevance far more accurately than the bi-encoder embeddings used for first-stage search.

```
50 cheap candidates ──► cross-encoder scores each (query,chunk) ──► keep top 8
   (high recall)              (high precision, ~50 LLM calls' worth of compute)
```

### 4.1 Hosted reranker (Cohere) — easiest

```python
import cohere
co = cohere.Client()

def rerank(query: str, candidates: list[str], top_n: int = 8) -> list[tuple[int, float]]:
    resp = co.rerank(model="rerank-v3.5", query=query, documents=candidates, top_n=top_n)
    return [(r.index, r.relevance_score) for r in resp.results]
```

### 4.2 Local reranker (no data leaves your network)

```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

def rerank_local(query, candidates, top_n=8):
    pairs = [(query, c) for c in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [(i, float(scores[i])) for i in ranked[:top_n]]
```

### 4.3 Why this is worth the latency

Reranking typically adds 50–200 ms but is consistently one of the largest quality
wins per dollar. **Always rerank** unless you're under a hard sub-100 ms budget. Pair it
with a **relevance-score floor** — drop candidates below a threshold so the LLM gets
"nothing relevant found" rather than garbage (a key hallucination guard, see [T06](06-guardrails-evals.md)).

```python
reranked = rerank(query, candidates, top_n=8)
kept = [(i, s) for i, s in reranked if s >= 0.2]   # tune the floor on your eval set
if not kept:
    return "I couldn't find anything relevant in the knowledge base."
```

---

## 5. Query rewriting & expansion

The user's raw question is often a *poor search query*. Rewriting bridges the gap
between how people ask and how documents are written.

### 5.1 The main techniques

| Technique | What it does | Use when |
|-----------|--------------|----------|
| **Rewrite** | clean/expand the query (fix typos, add synonyms) | always cheap to try |
| **Multi-query** | generate N paraphrases, retrieve for each, union | recall-critical |
| **HyDE** | generate a *hypothetical answer*, embed that | sparse/short queries |
| **Decomposition** | split a multi-part question into sub-questions | complex/comparative Qs |
| **Contextualization** | rewrite a follow-up into a standalone query | multi-turn chat |

### 5.2 Conversational rewrite (the one you can't skip in chat)

In multi-turn chat, "what about the second one?" is meaningless to a retriever. Rewrite
it into a standalone query using the history **before** searching:

```python
REWRITE = """Given the conversation, rewrite the user's last message into a standalone
search query that captures full intent. Output only the query.

Conversation:
{history}

Standalone query:"""

standalone = llm.invoke(REWRITE.format(history=format_history(messages))).content
docs = hybrid_retrieve(standalone)
```

### 5.3 Multi-query expansion

```python
MULTI = """Generate 3 diverse search queries that capture different facets of:
"{q}"
Return one per line."""

variants = [q.strip() for q in llm.invoke(MULTI.format(q=question)).content.splitlines() if q.strip()]
all_ids = reciprocal_rank_fusion([hybrid_retrieve(v) for v in [question, *variants]])
```

### 5.4 HyDE (Hypothetical Document Embeddings)

Short queries embed poorly. Generate a fake "ideal answer," embed *that*, and search —
it lands closer to real answer passages in vector space.

```python
HYDE = "Write a short factual paragraph that would answer: {q}"
hypothetical = llm.invoke(HYDE.format(q=question)).content
docs = vector_search_by_text(hypothetical, top_k=50)   # embed the hypothetical, not the query
```

**Cost/latency caveat:** every rewrite technique adds an LLM call before retrieval.
Use a fast cheap model (Haiku), cache aggressively (see [T07](07-fastapi-microservices.md)),
and measure on your eval set — don't stack all four blindly.

---

## 6. Generation: prompt assembly & faithful answering

Retrieval done — now construct the prompt. Three rules:

1. **Number the sources** so the model can cite them.
2. **Instruct grounding explicitly** — answer only from context; say "I don't know" otherwise.
3. **Put the question last** (recency helps instruction following).

```python
def build_prompt(question: str, chunks: list[dict]) -> str:
    ctx = "\n\n".join(
        f"[{i+1}] (source: {c['metadata']['title']}, p.{c['metadata'].get('page','?')})\n{c['text']}"
        for i, c in enumerate(chunks)
    )
    return f"""Answer the question using ONLY the sources below. Cite sources inline as [1], [2].
If the sources do not contain the answer, say "I don't have that information." Do not use outside knowledge.

Sources:
{ctx}

Question: {question}"""
```

```python
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0, max_tokens=1024)
answer = llm.invoke(build_prompt(question, kept_chunks)).content
```

> Citation enforcement, "answer-supported-by-context" checks, and hallucination
> detection live in [T06 — Guardrails & Evals](06-guardrails-evals.md).

---

## 7. Putting it all together

```python
def rag_answer(question: str, messages=None, tenant_id="default") -> dict:
    # 1. rewrite (standalone if conversational)
    query = rewrite_standalone(question, messages) if messages else question

    # 2. hybrid retrieve with tenant + ACL filter (T03, T09)
    candidates = hybrid_retrieve(query, top_k=50, filters={"tenant_id": tenant_id})

    # 3. rerank → precise top-k, with a relevance floor
    kept = [candidates[i] for i, s in rerank(query, [c["text"] for c in candidates]) if s >= 0.2]
    if not kept:
        return {"answer": "I couldn't find anything relevant.", "sources": []}

    # 4. generate grounded answer
    answer = llm.invoke(build_prompt(question, kept)).content
    return {"answer": answer, "sources": [c["metadata"] for c in kept]}
```

---

## 8. Production checklist & pitfalls

- [ ] **Chunk on structure, not characters.** Carry the heading path in metadata.
- [ ] **Always go hybrid.** Pure-vector misses codes/IDs/names users actually search.
- [ ] **Always rerank** (unless <100 ms budget) and apply a relevance floor.
- [ ] **Rewrite conversational queries** before retrieving — non-negotiable for chat.
- [ ] **Tag every chunk** with tenant_id + ACL at ingest (retro-fitting is painful).
- [ ] **Measure, don't guess.** Track retrieval recall@k separately from answer quality (T06).
- [ ] **Watch context bloat.** More chunks ≠ better; irrelevant context degrades answers ("lost in the middle").
- [ ] **Re-embed on model change.** Embeddings from different models are incompatible — version your index.

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Right doc exists but never retrieved | chunking shredded it / pure-vector blind to exact terms | structure chunking + hybrid |
| Retrieves loosely related junk | no reranking / no score floor | add reranker + threshold |
| Good chunks, wrong answer | context too long, key chunk buried | fewer chunks, rerank order, smaller top-k |
| Chat follow-ups fail | no query contextualization | rewrite to standalone |
| Answers cite nonexistent facts | no grounding instruction / no "I don't know" path | strengthen prompt + guards (T06) |

**Next:** [02 — Document Ingestion](02-document-ingestion.md) — getting clean text and
structure out of messy PDFs, DOCX, and scans, which is what feeds everything above.
