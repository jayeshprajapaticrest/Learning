# 03 — Vector Search Systems (Qdrant / Weaviate / OpenSearch)

> **Goal:** Store embeddings so you can retrieve the right chunks in milliseconds at
> scale — with metadata filtering, hybrid search, and multi-tenant isolation. We compare
> Qdrant, Weaviate, and OpenSearch and give production-tuned code for each.

---

## 1. Core concepts (the 5-minute foundation)

- **Embedding:** a chunk → a fixed-length vector (e.g. 1024 floats) where *semantic
  similarity ≈ geometric closeness*.
- **ANN (Approximate Nearest Neighbor):** exact nearest-neighbor over millions of
  vectors is too slow, so we use approximate indexes — trading a tiny bit of recall for
  100–1000× speed. **HNSW** (a navigable graph) is the dominant algorithm.
- **Distance metric:** **cosine** is the default for text embeddings. Must match what
  the embedding model was trained for.
- **Payload/metadata:** structured fields stored beside the vector (tenant_id, ACL,
  page, doc_type) used for **filtering** — the backbone of multi-tenancy ([T05](05-knowledge-layers.md))
  and security ([T09](09-security-governance.md)).

```
query text ──embed──► query vector ──ANN search (HNSW) + filter──► top-k chunk ids + payload
```

### HNSW knobs you'll actually touch

| Param | Meaning | Effect |
|-------|---------|--------|
| `m` | edges per node | higher = better recall, more memory |
| `ef_construct` | candidate list at build | higher = better index, slower build |
| `ef` / `ef_search` | candidate list at query | higher = better recall, slower query |

Tune `ef_search` per query for the recall/latency trade-off; raise `m`/`ef_construct`
once at build time for a higher-quality index.

---

## 2. Choosing an engine

| | **Qdrant** | **Weaviate** | **OpenSearch** |
|---|-----------|--------------|----------------|
| Written in | Rust | Go | Java (Lucene) |
| Sweet spot | fast, lean vector-first service | vectors + built-in hybrid + modules | already-have-Elastic shops, keyword+vector |
| Hybrid search | sparse vectors (BM42/SPLADE) + dense | native `alpha` blend | native BM25 + kNN |
| Multi-tenancy | payload partitioning + named tenants | first-class tenants (per-tenant shards) | index-per-tenant / filter |
| Filtering | excellent, payload indexes | good | excellent (mature query DSL) |
| Quantization | scalar / product / binary | PQ / BQ | PQ / scalar |
| Ops | simplest single binary / cloud | moderate | heaviest (JVM) but familiar |

**Quick guidance:** default to **Qdrant** for a new RAG service (fast, simple, great
filtering). Pick **Weaviate** if you want hybrid + GraphQL + modules out of the box.
Pick **OpenSearch** if you already run Elastic/OpenSearch and want one system for
keyword + vector + logs.

---

## 3. Qdrant (recommended default)

### 3.1 Create a collection (tuned)

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(url="http://localhost:6333")

client.create_collection(
    collection_name="kb",
    vectors_config=models.VectorParams(
        size=1024, distance=models.Distance.COSINE,
        # store vectors on disk + keep HNSW in RAM → cheaper at scale
        on_disk=True,
    ),
    hnsw_config=models.HnswConfigDiff(m=16, ef_construct=200),
    # scalar quantization: 4x smaller, ~minimal recall loss, big cost win
    quantization_config=models.ScalarQuantization(
        scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=True)
    ),
    # ENABLE hybrid: add a named sparse vector too
    sparse_vectors_config={"bm42": models.SparseVectorParams()},
)
# index the fields you filter on → fast filtered search + multi-tenancy
client.create_payload_index("kb", "tenant_id", models.PayloadSchemaType.KEYWORD)
client.create_payload_index("kb", "doc_type", models.PayloadSchemaType.KEYWORD)
```

### 3.2 Upsert chunks

```python
client.upsert("kb", points=[
    models.PointStruct(
        id=chunk_id,                                   # uuid or content hash
        vector=dense_vector,                            # from your embedding model
        payload={"text": chunk_text, "tenant_id": "acme", "doc_type": "policy",
                 "title": "Leave Policy", "page": 7,
                 "acl": ["group:hr"], "updated_at": "2026-03-01"},
    )
    for chunk_id, dense_vector, chunk_text in batch
])
```

### 3.3 Filtered dense search (multi-tenant + ACL)

```python
hits = client.query_points(
    "kb", query=query_vector, limit=50,
    query_filter=models.Filter(must=[
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value="acme")),
        models.FieldCondition(key="acl", match=models.MatchAny(any=user_groups)),
    ]),
    search_params=models.SearchParams(hnsw_ef=128),     # recall/latency knob
).points
```

> **Filtering is a security boundary, not a nicety.** The `tenant_id` + `acl` filter is
> what stops tenant A from reading tenant B's data. Apply it server-side, always. See
> [T09](09-security-governance.md).

### 3.4 Native hybrid search with server-side fusion

Qdrant can run dense + sparse and fuse with RRF in one call — no client-side fusion:

```python
hits = client.query_points(
    "kb", limit=10,
    prefetch=[
        models.Prefetch(query=query_vector, using="", limit=50),               # dense
        models.Prefetch(query=sparse_query, using="bm42", limit=50),           # sparse
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    query_filter=tenant_filter,
).points
```

---

## 4. Weaviate (batteries-included hybrid + tenancy)

```python
import weaviate
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.tenants import Tenant

client = weaviate.connect_to_local()

client.collections.create(
    "KB",
    vector_index_config=Configure.VectorIndex.hnsw(
        distance_metric=weaviate.classes.config.VectorDistances.COSINE,
        quantizer=Configure.VectorIndex.Quantizer.bq(),   # binary quantization
    ),
    multi_tenancy_config=Configure.multi_tenancy(enabled=True),  # first-class tenants
    properties=[
        Property(name="text", data_type=DataType.TEXT),
        Property(name="title", data_type=DataType.TEXT),
        Property(name="page", data_type=DataType.INT),
    ],
)

kb = client.collections.get("KB")
kb.tenants.create([Tenant(name="acme"), Tenant(name="globex")])  # isolated per tenant

# Native hybrid: alpha=0 pure keyword, alpha=1 pure vector, 0.5 balanced
results = kb.with_tenant("acme").query.hybrid(
    query="parental leave eligibility", alpha=0.5, limit=10,
    vector=query_vector,
)
```

Weaviate's **per-tenant isolation** is its standout enterprise feature: each tenant gets
its own shard, so you can onboard/offload tenants and the blast radius of a bad query
stays contained.

---

## 5. OpenSearch (when you already run Elastic-style infra)

```python
from opensearchpy import OpenSearch
os_client = OpenSearch(hosts=[{"host": "localhost", "port": 9200}])

os_client.indices.create("kb", body={
    "settings": {"index": {"knn": True}},
    "mappings": {"properties": {
        "text": {"type": "text"},                       # BM25 keyword side
        "tenant_id": {"type": "keyword"},
        "embedding": {"type": "knn_vector", "dimension": 1024,
                      "method": {"name": "hnsw", "engine": "lucene",
                                 "space_type": "cosinesimil",
                                 "parameters": {"m": 16, "ef_construction": 200}}},
    }},
})

# Hybrid: combine BM25 + kNN. Use a search pipeline with normalization-processor in prod.
body = {"size": 10, "query": {"bool": {
    "filter": [{"term": {"tenant_id": "acme"}}],
    "should": [
        {"match": {"text": {"query": "parental leave eligibility"}}},   # BM25
        {"knn": {"embedding": {"vector": query_vector, "k": 50}}},      # vector
    ]}}}
hits = os_client.search(index="kb", body=body)["hits"]["hits"]
```

OpenSearch shines when you want **one system** for full-text, vector, and log/analytics,
with a mature query DSL and RBAC you may already operate.

---

## 6. Embeddings: the input that determines everything

Your index is only as good as the embeddings.

| Model | Dim | Notes |
|-------|-----|-------|
| `text-embedding-3-large` (OpenAI) | 3072 (truncatable) | strong general default |
| `voyage-3` / `voyage-3-large` | 1024 | top retrieval quality, long context |
| `bge-m3` (local) | 1024 | multilingual, dense+sparse+colbert, on-prem |
| Cohere `embed-v4` | configurable | strong, multimodal options |

```python
from langchain_openai import OpenAIEmbeddings
emb = OpenAIEmbeddings(model="text-embedding-3-large", dimensions=1024)  # truncate to save space
vectors = emb.embed_documents([c["text"] for c in chunks])
```

Rules:
- **Use the same model for indexing and querying.** Mismatched models = nonsense results.
- **Version your index** by embedding model. Changing models means a **full re-embed** —
  plan for blue/green reindexing, not in-place mutation.
- **Normalize** if your metric/model expects it (most cosine setups handle this for you).
- **Batch** embedding calls and handle rate limits with retry/backoff (see [T07](07-fastapi-microservices.md)).

---

## 7. Scaling, cost & latency

| Lever | What it does | Trade-off |
|-------|--------------|-----------|
| **Quantization** (scalar/PQ/binary) | 4–32× smaller vectors | tiny recall loss |
| **On-disk vectors** | RAM holds only the graph | slightly slower, much cheaper |
| **Sharding** | spread vectors across nodes | operational complexity |
| **Lower dim** (Matryoshka/truncation) | smaller + faster | small quality loss |
| **`ef_search` tuning** | recall vs latency per query | direct dial |
| **Replicas** | throughput + HA | cost |

Rough capacity intuition: 1M chunks × 1024-dim float32 ≈ 4 GB raw; **int8 scalar
quantization** drops that to ~1 GB and binary to ~128 MB — the difference between fitting
in RAM cheaply or not. Always benchmark recall on *your* data after quantizing.

---

## 8. Multi-tenancy patterns (preview of [T05](05-knowledge-layers.md))

| Pattern | Isolation | Cost | Use when |
|---------|-----------|------|----------|
| **Shared collection + `tenant_id` filter** | logical (filter) | lowest | many small tenants |
| **Collection/index per tenant** | strong | higher | few large tenants, strict isolation |
| **Native tenants** (Weaviate) | strong, managed | medium | many tenants, want managed isolation |

Whichever you choose, the `tenant_id` filter must be **enforced server-side from the
authenticated identity** — never trust a tenant id sent by the client. This is the #1
multi-tenant RAG security mistake.

---

## 9. Checklist

- [ ] Cosine distance + HNSW; tune `m`/`ef_construct` at build, `ef_search` at query.
- [ ] Quantize (start with int8 scalar) and benchmark recall on your data.
- [ ] Create payload/field indexes on every filtered field (tenant_id, acl, doc_type).
- [ ] Enable hybrid (sparse+dense) with server-side RRF where the engine supports it.
- [ ] Same embedding model for index + query; version the index per model.
- [ ] Enforce tenant_id + ACL filters server-side from the auth context.
- [ ] Plan blue/green reindex for embedding-model upgrades.
- [ ] Monitor recall@k, p95 latency, and index memory.

**Next:** [04 — LangGraph Agentic Workflows](04-langgraph-agents.md) — using retrieval as
one tool among many inside planning, tool-using, self-healing agents.
