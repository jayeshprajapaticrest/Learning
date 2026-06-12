# Architecture Review 3 — Enterprise RAG Platform

> **Difficulty:** Architect | **Related Modules:** 06, 07, 12, 14, 16, 18

---

## Instructions

You are an AI Architect reviewing a proposed enterprise RAG platform before the team begins development. A VP of Engineering has asked you to provide written feedback. Your task:

1. Read the design carefully
2. Identify **all architectural flaws** (there are exactly **10 seeded flaws**)
3. For each flaw: state the flaw, classify it (security / reliability / scalability / cost / quality), and propose a fix
4. Compare your findings to the model answer

---

## Design Document Under Review

### System Overview

An enterprise deploys a RAG platform serving 20 internal business units. Each BU uploads documents to a shared knowledge base. Employees ask questions; the system retrieves relevant documents and answers using the company's internal AI assistant.

**Scale:** 5,000 daily active users, 2M documents, 50K queries per day

### Vector Database Design

```python
# Single Qdrant collection for all documents
collection = qdrant_client.create_collection(
    collection_name="enterprise_kb",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

def ingest_document(doc_id, text, embedding, business_unit, department):
    qdrant_client.upsert(
        collection_name="enterprise_kb",
        points=[PointStruct(
            id=doc_id,
            vector=embedding,
            payload={
                "business_unit": business_unit,
                "department": department,
                "text": doc_chunk,
            }
        )]
    )

def search(query_embedding, business_unit):
    return qdrant_client.search(
        collection_name="enterprise_kb",
        query_vector=query_embedding,
        limit=10,
        query_filter=Filter(
            must=[FieldCondition(key="business_unit", value=MatchValue(value=business_unit))]
        )
    )
```

### Retrieval Pipeline

```python
def retrieve_and_answer(user_query: str, user_id: str, business_unit: str) -> str:
    # Embed the query
    embedding = openai_client.embeddings.create(
        model="text-embedding-ada-002",
        input=user_query
    ).data[0].embedding
    
    # Search (dense only)
    results = search(embedding, business_unit)
    
    # Build context
    context = "\n\n".join([r.payload["text"] for r in results])
    
    # Answer
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system="You are a helpful enterprise assistant. Answer based on the provided context.",
        messages=[{
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {user_query}"
        }]
    )
    return response.content[0].text
```

### Chunking Strategy

```python
def chunk_document(text: str) -> list[str]:
    # Split by character count
    chunk_size = 500
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i + chunk_size])
    return chunks
```

### Embedding Model

- Using OpenAI `text-embedding-ada-002` for all embeddings
- No fallback if OpenAI is unavailable
- Query embeddings and document embeddings generated on every request (no caching)

### Memory / Context

- No conversation memory implemented
- Each query is treated as independent
- No query history stored

### Ingestion Pipeline

```python
def ingest_all_documents(documents: list[dict]):
    # Process one at a time
    for doc in documents:
        chunks = chunk_document(doc["text"])
        for chunk in chunks:
            embedding = get_embedding(chunk)
            ingest_document(doc["id"], chunk, embedding, doc["business_unit"])
    print("Ingestion complete")
```

### Access Control

```python
def retrieve_and_answer(user_query: str, user_id: str, business_unit: str) -> str:
    # business_unit passed by client in HTTP header
    # No server-side verification of user's BU membership
    business_unit = request.headers.get("X-Business-Unit")
    ...
```

### Evaluation

- Evaluation: manually review 5 questions per month
- No automated RAGAS metrics
- No retrieval quality metrics (precision@k, recall@k)
- No faithfulness checking (answers may contain hallucinations)

### Reliability

- Single Qdrant instance (no replication)
- No circuit breaker for the LLM call
- No fallback if Qdrant is down
- SLA: "best effort"

### Cost

- No request-level cost tracking
- No per-BU cost attribution
- At 50K queries/day: estimated cost not calculated

---

## Your Task

Find and document all 10 architectural flaws. For each flaw, include:
- **Category**: Security | Reliability | Quality | Cost | Scalability
- **What is the flaw?**
- **What is the risk?**
- **How would you fix it?**

---

---

---

*(Model answer below — do not read until you have found all 10 flaws)*

---

---

---

## Model Answer

### Flaw 1 — Security: Business unit isolation enforced via client-supplied header only

**Category:** Security (Critical)

**What:** `business_unit = request.headers.get("X-Business-Unit")`. The business unit used for filtering is taken directly from the HTTP request header with no server-side verification that the authenticated user actually belongs to that BU.

**Risk:** Any authenticated employee can change the `X-Business-Unit` header to `"Legal"`, `"Finance"`, or any other BU and retrieve documents they are not authorized to access. This bypasses the entire access control model. In an enterprise context, Finance/Legal documents accessed by unauthorized employees is a compliance failure (SOX, attorney-client privilege).

**Fix:**
1. Never trust client-supplied BU claims. Look up the authenticated user's BU membership from the identity store (Active Directory, Okta) server-side
2. JWT validation: the user's BU memberships should be in the JWT claims, signed by the identity provider
3. Row-level filtering in Qdrant should use the server-resolved BU list, not a client-supplied value
4. Consider per-BU collections (Module 14 pattern) for hard isolation rather than metadata filtering

---

### Flaw 2 — Quality: Fixed character chunking destroys semantic coherence

**Category:** Quality

**What:** Documents are chunked at exactly 500 characters, splitting mid-sentence and mid-paragraph.

**Risk:**
1. A sentence like "The maximum liability is $5,000,000 per incident under Article 7.2" becomes two chunks: one ending at "per incident" and another starting at "under Article 7.2". Neither chunk contains the complete fact.
2. Retrieval quality degrades significantly when chunks break semantic units
3. The model answers from incomplete context fragments, increasing hallucination risk

**Fix:**
1. Semantic chunking: split on sentence/paragraph boundaries using `nltk.sent_tokenize` or spaCy
2. Token-aware chunking: use `tiktoken` to chunk at ~300 tokens with 50-token overlap
3. Overlap: consecutive chunks share context so cross-chunk facts are not lost
4. Structure-aware: for PDFs, respect section headings; don't break a heading from its first paragraph

---

### Flaw 3 — Quality: Dense-only retrieval — keyword and exact-match queries fail

**Category:** Quality

**What:** Retrieval uses only dense vector search (`text-embedding-ada-002`). There is no BM25/keyword search component.

**Risk:**
1. Exact-match queries fail: "Show me contract IC-2024-0042" returns semantically similar contracts, not the exact one by ID
2. Technical term queries fail: "GDPR Article 17 right to erasure" may not match documents that use the exact legal terminology
3. Dense retrieval excels at semantic similarity; it underperforms on exact entity and keyword queries

**Fix:**
1. Hybrid retrieval: combine BM25 (keyword) + dense (semantic) with Reciprocal Rank Fusion
2. Elasticsearch or Qdrant sparse vectors for the BM25 component
3. Re-ranking: cross-encoder re-ranker (Cohere Rerank or a fine-tuned model) on the top-20 merged results → select top 5
4. This is the hybrid search pattern from Module 07

---

### Flaw 4 — Quality: No faithfulness checking — hallucinations pass through undetected

**Category:** Quality / Risk

**What:** The model's answer is returned directly to the user. There is no check that the answer is grounded in the retrieved context.

**Risk:**
1. The model may hallucinate facts that are not in any retrieved chunk
2. In an enterprise context, employees may act on hallucinated policy information (HR, Legal, Finance)
3. No way to detect systematic hallucination after a model update

**Fix:**
1. Faithfulness check: after generating the answer, pass `(context, answer)` to a faithfulness judge prompt: "Is every claim in the answer supported by the context? Rate: supported/partially_supported/not_supported"
2. Citation enforcement: require the model to cite which chunk supports each claim (Module 07)
3. If faithfulness score < threshold → answer "I found relevant documents but cannot give a confident answer; please consult the source document"
4. Track faithfulness metric over time; alert on degradation

---

### Flaw 5 — Reliability: Single Qdrant instance — SPOF for the entire platform

**Category:** Reliability

**What:** Single Qdrant instance with no replication. If it fails, all 50K queries/day fail.

**Risk:**
1. Any Qdrant instance failure (hardware, update, crash) takes down the entire RAG platform
2. No replication means data is also at risk — a disk failure could lose all 2M document embeddings
3. 2M re-embeddings at recovery time = hours of downtime + significant cost

**Fix:**
1. Qdrant cluster with replication factor ≥ 2
2. Regular vector index snapshots to durable storage (S3)
3. Alternative: managed vector DB with built-in HA (Pinecone, Weaviate Cloud, Qdrant Cloud)
4. Degrade gracefully: if Qdrant is unavailable, return a "knowledge base temporarily unavailable" message rather than an unhandled error

---

### Flaw 6 — Reliability: No fallback for OpenAI embedding API — outage breaks ingestion and querying

**Category:** Reliability

**What:** OpenAI `text-embedding-ada-002` is the sole embedding provider with no fallback.

**Risk:**
1. OpenAI outages (which occur multiple times per year) stop all query processing
2. Ingestion halts during outages, creating a backlog
3. The embedding model may be deprecated (OpenAI has deprecated previous embedding models)
4. Vendor lock-in: all 2M document embeddings are generated with one specific model's vector space; switching models requires re-embedding everything

**Fix:**
1. Fallback embedding model: if OpenAI is unavailable, fall back to a local embedding model (sentence-transformers, Cohere)
2. Note: fallback must use a separate collection if vector dimensions differ
3. Circuit breaker: on repeated OpenAI failures, route to fallback for N minutes
4. Long-term: consider a self-hosted embedding model for cost and independence

---

### Flaw 7 — Scalability: Sequential ingestion pipeline — 2M documents would take days

**Category:** Scalability

**What:** `ingest_all_documents` processes one document at a time in a loop. No parallelism.

**Risk:**
1. 2M documents × (embedding API latency ~100ms + Qdrant upsert ~5ms) = 200,000+ seconds ≈ 55+ hours for initial ingestion
2. Backlog builds during business hours when new documents arrive faster than sequential ingestion can process them
3. No progress tracking — if it fails at document 1.5M, there is no way to resume

**Fix:**
1. Parallel ingestion: `asyncio.gather` or a worker pool (20 concurrent embedding calls)
2. Batching: OpenAI and Qdrant both support batch operations — embed 100 chunks per API call, upsert 100 points per Qdrant call
3. Resumable: track ingestion state in Postgres (doc_id, status: pending/complete/failed)
4. With batching + parallelism, 2M chunks can be ingested in hours, not days

---

### Flaw 8 — Cost: Query embedding not cached — 50K embeddings per day is avoidable waste

**Category:** Cost

**What:** Every query generates a fresh embedding via the OpenAI API. No caching.

**Risk:**
1. Enterprise users ask similar questions repeatedly (e.g., "What is the PTO policy?" asked by hundreds of employees)
2. 50K queries/day × embedding cost (~$0.0001 each) = $5/day × 365 = $1,825/year on embeddings alone
3. More importantly: semantic caching can serve the full LLM answer from cache, saving 10-100× more

**Fix:**
1. Semantic query cache (Module 16): embed the query; search the cache (a small Qdrant collection) for a similar past query (cosine similarity > 0.95); return cached answer
2. Cache hit rate for enterprise queries (similar questions asked repeatedly) is often 30-60%
3. At 40% cache hit rate: save 40% of both embedding and LLM costs
4. Cache TTL: 24 hours (policy documents don't change intraday); invalidate on document update

---

### Flaw 9 — Cost: No per-BU cost attribution — cannot charge back or monitor usage

**Category:** Cost / Governance

**What:** There is no per-request or per-BU cost tracking. With 20 BUs sharing the platform, there is no way to allocate costs.

**Risk:**
1. One BU ingesting 1.8M of the 2M documents and making 45K of 50K queries carries no incremental cost — all 20 BUs split the bill equally
2. No visibility into which BU is driving cost growth
3. Cannot implement budget limits per BU
4. CFO will reject a platform budget request that cannot explain cost drivers

**Fix:**
1. Track per-request: `{user_id, business_unit, query_embedding_tokens, context_tokens, answer_tokens, total_cost_usd, timestamp}`
2. Postgres table for cost records; daily rollup view per BU
3. Monthly report: cost per BU; per-query average cost trend
4. Alert: if any BU's daily cost exceeds threshold, notify the BU admin

---

### Flaw 10 — Evaluation: 5 manual reviews per month — cannot detect quality regressions

**Category:** Quality / Operations

**What:** Quality assurance relies on 5 manually reviewed questions per month. No automated metrics.

**Risk:**
1. A model provider update, chunking change, or embedding model change can degrade quality immediately; 5 manual reviews per month would catch this weeks later
2. 5 samples is statistically insufficient to characterize quality across 20 BUs × diverse document types
3. No retrieval metrics: even if the LLM answer is good, irrelevant retrieval is masked
4. No way to run A/B tests on retrieval improvements

**Fix:**
1. Golden dataset: 100+ labeled (question, expected_answer, relevant_doc_ids) pairs
2. Automated eval run on every code change: faithfulness, answer relevance, context precision, context recall (RAGAS metrics)
3. Retrieval metrics: precision@5, recall@10 (do the retrieved chunks contain the answer?)
4. Continuous monitoring: sample 0.5% of production queries; LLM-as-judge rates each answer
5. Alert on any metric degradation > 5% from baseline

---

## Scoring Guide

| Flaws Found | Assessment |
|-------------|------------|
| 9-10 | Architect: cost, security, quality, reliability all covered; can write the tech spec |
| 7-8 | Principal: missed one dimension (usually cost attribution or evaluation) |
| 5-6 | Staff: caught infrastructure + retrieval quality; missed cost and security detail |
| 3-4 | Senior: caught retrieval issues; missed enterprise-specific concerns |

The hardest flaws to spot are typically: Flaw 1 (client-supplied BU header — requires security paranoia), Flaw 9 (cost attribution as a governance requirement), and Flaw 4 (faithfulness checking — requires knowing that RAG systems hallucinate even with good retrieval). These distinguish Staff from Architect thinking.
