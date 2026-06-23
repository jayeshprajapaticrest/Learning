# 07 — FastAPI AI Microservices (Async, Caching, Streaming)

> **Goal:** Serve your RAG/agent system as a production HTTP service that's **async**
> (handles concurrency without blocking), **cached** (cheap and fast), **streaming**
> (responsive UX), and **observable**. FastAPI is the de-facto standard for Python AI APIs.

---

## 1. Why async matters for AI services

AI requests are **I/O-bound**: most of the time is spent *waiting* on the LLM, vector DB,
and external APIs — not computing. With synchronous code, one slow LLM call blocks an
entire worker. With **async**, one process juggles hundreds of in-flight requests while
they wait on I/O. For LLM services where calls take seconds, this is the difference
between 5 and 500 concurrent users per process.

```
 sync:   req1 ──wait LLM 3s── done | req2 ──wait 3s── done   (serial, worker blocked)
 async:  req1 ──wait LLM 3s───────► done
         req2 ──wait LLM 3s───────► done   (overlapped — worker free during waits)
         req3 ──wait LLM 3s───────► done
```

**The golden rule: never block the event loop.** One synchronous CPU-heavy or
blocking-I/O call (a sync DB driver, `time.sleep`, a CPU reranker) stalls *every*
concurrent request on that worker. Use `async def` + async clients, and offload blocking
work to a thread/process pool.

---

## 2. Project skeleton

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
import httpx, redis.asyncio as aioredis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # init shared, reusable clients ONCE at startup (not per request)
    app.state.redis = aioredis.from_url("redis://localhost", decode_responses=True)
    app.state.http = httpx.AsyncClient(timeout=30)           # connection pooling
    app.state.llm = make_llm_client()
    yield
    await app.state.redis.aclose()
    await app.state.http.aclose()

app = FastAPI(title="AI Service", lifespan=lifespan)

class AskRequest(BaseModel):
    question: str
    session_id: str | None = None

class AskResponse(BaseModel):
    answer: str
    sources: list[dict]
    cached: bool = False
```

Key points: **create clients once** in `lifespan` and reuse them (creating an HTTP/LLM
client per request destroys performance and leaks connections); use **Pydantic models**
for typed, validated, auto-documented request/response.

---

## 3. The endpoint (async, with dependencies)

```python
async def get_principal(authorization: str = Header(...)) -> "Principal":
    return await verify_jwt(authorization)        # auth → tenant_id + groups (T09)

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, principal=Depends(get_principal)):
    ok, msg = input_guards(req.question, principal)         # T06
    if not ok:
        raise HTTPException(400, msg)
    result = await rag_answer_async(req.question, principal) # T01, async all the way down
    return AskResponse(**result)
```

If a library is **sync-only** (a CPU reranker, a blocking SDK), offload it so it doesn't
block the loop:

```python
from fastapi.concurrency import run_in_threadpool
scores = await run_in_threadpool(local_reranker.predict, pairs)   # T01 §4.2
```

---

## 4. Caching — the biggest cost & latency win

LLM and embedding calls are slow and metered. Cache aggressively at multiple layers.

### 4.1 Layers of caching

| Layer | Caches | TTL | Win |
|-------|--------|-----|-----|
| **Embedding cache** | text → vector | long (content-keyed) | skip re-embedding identical text |
| **Retrieval cache** | query → chunk ids | minutes | skip vector search |
| **Full-response cache** | (query, tenant) → answer | minutes–hours | skip everything |
| **Semantic cache** | *similar* query → answer | minutes | hit on paraphrases |
| **Provider prompt cache** | repeated prompt prefixes | provider-managed | cheaper tokens, lower latency |

### 4.2 Exact-match response cache (Redis)

```python
import hashlib, json

def cache_key(question: str, principal) -> str:
    # ALWAYS scope the key by tenant — never serve tenant A's answer to tenant B
    raw = f"{principal.tenant_id}:{question.strip().lower()}"
    return "ans:" + hashlib.sha256(raw.encode()).hexdigest()

async def cached_ask(req, principal, redis) -> dict:
    key = cache_key(req.question, principal)
    if hit := await redis.get(key):
        return {**json.loads(hit), "cached": True}
    result = await rag_answer_async(req.question, principal)
    await redis.set(key, json.dumps(result), ex=3600)        # 1h TTL
    return result
```

### 4.3 Semantic cache (hit on paraphrases)

Embed the query; if a past query is very close in vector space, reuse its answer:

```python
async def semantic_cache_get(query_vec, tenant_id, threshold=0.97):
    hits = await cache_vectorstore.search(query_vec, filter={"tenant_id": tenant_id}, k=1)
    if hits and hits[0].score >= threshold:
        return hits[0].payload["answer"]
    return None
```

Caution: set the threshold **high** (≥0.95). A loose semantic cache returns subtly wrong
answers to different questions — worse than a miss. Always tenant-scope cache keys.

### 4.4 Provider prompt caching

Claude (and others) cache repeated prompt prefixes — your system prompt, tool defs,
few-shot examples, or a large retrieved document. Mark the stable prefix as cacheable to
cut both latency and token cost on every request. Pairs naturally with the contextual-
chunking pattern in [T01 §2.5](01-rag-pipelines.md).

---

## 5. Streaming responses

Users shouldn't stare at a spinner for 5 seconds. Stream tokens as they're generated —
perceived latency drops dramatically. Use **SSE** (simple, HTTP) or WebSockets (bidirectional).

```python
from fastapi.responses import StreamingResponse

@app.post("/ask/stream")
async def ask_stream(req: AskRequest, principal=Depends(get_principal)):
    async def gen():
        async for event in rag_stream(req.question, principal):
            if event.type == "token":
                yield f"data: {json.dumps({'token': event.text})}\n\n"
            elif event.type == "sources":
                yield f"data: {json.dumps({'sources': event.data})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

For agents (T04), stream **intermediate steps** too ("searching knowledge base…",
"checking CRM…") so long runs feel alive.

---

## 6. Reliability: timeouts, retries, rate limits, concurrency

External LLM/DB calls *will* fail or rate-limit. Build for it.

```python
import asyncio
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

@retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(4),
       retry=retry_if_exception_type(RateLimitError))
async def call_llm(prompt):
    return await llm.ainvoke(prompt)

# Cap concurrent upstream calls so you don't blow provider rate limits or your own memory
LLM_SEM = asyncio.Semaphore(20)
async def guarded_llm(prompt):
    async with LLM_SEM:
        return await call_llm(prompt)
```

Also essential:
- **Timeouts on every external call** — a hung upstream must not pin a request forever.
- **Circuit breaker / graceful degradation** — if the LLM is down, return a clear error
  or a cached/fallback answer, not a 30s hang.
- **Per-tenant rate limiting** (e.g. via Redis token bucket) to prevent one tenant
  starving others and to control cost.
- **Idempotency keys** on mutating endpoints so client retries don't double-act.

---

## 7. Background work & long tasks

Ingestion ([T02](02-document-ingestion.md)) and big agent runs shouldn't block an HTTP
request. Return `202 Accepted` + a job id; process via a queue worker; let the client poll
or get a webhook/SSE.

```python
@app.post("/ingest", status_code=202)
async def ingest(req: IngestRequest, principal=Depends(get_principal)):
    job_id = await enqueue_ingest(req.source_uri, principal.tenant_id)   # Celery/Arq/RQ
    return {"job_id": job_id, "status_url": f"/jobs/{job_id}"}
```

Use **FastAPI `BackgroundTasks`** only for short fire-and-forget work (e.g. logging); use
a real task queue (**Celery / Arq / RQ / Dramatiq**) for anything heavy or that must survive
restarts.

---

## 8. Observability & deployment

- **Health/readiness:** `/healthz` (process up) + `/readyz` (deps reachable) for k8s probes.
- **Metrics:** Prometheus — request rate, p50/p95/p99 latency, error rate, cache hit
  rate, tokens & cost per request, queue depth.
- **Tracing:** OpenTelemetry spanning API → retrieval → LLM → tools (ties into agent
  tracing, T04 §9).
- **Structured logs** with a request id + tenant id on every line for debugging and audit (T09).

```dockerfile
# Run multiple async workers; each handles many concurrent requests
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Deployment notes: scale **horizontally** (stateless pods behind a load balancer; keep
session/agent state in Redis/Postgres, not in-process — see T04 checkpointing). Right-size
workers to cores; set graceful shutdown so in-flight streams finish. Autoscale on
latency/queue-depth, not just CPU (AI services are I/O-bound, so CPU is a poor signal).

---

## 9. Checklist

- [ ] `async def` end-to-end; never block the event loop; offload sync/CPU work to a pool.
- [ ] Init clients once in `lifespan`; reuse pooled HTTP/LLM/DB/Redis clients.
- [ ] Pydantic models for validated, documented request/response.
- [ ] Multi-layer caching (embedding, retrieval, response, semantic, provider) — tenant-scoped keys.
- [ ] Stream tokens (SSE/WS); stream agent intermediate steps.
- [ ] Timeouts + retries/backoff + semaphores + per-tenant rate limits + circuit breaker.
- [ ] Heavy work → task queue with job status; short fire-and-forget → BackgroundTasks.
- [ ] Health/readiness probes, metrics, tracing, structured logs with request+tenant id.
- [ ] Stateless pods; external state store; horizontal autoscale on latency/queue depth.

**Next:** [08 — Enterprise Integration & MCP](08-enterprise-integration.md) — connecting
this service to SharePoint, CRMs, databases, and MCP tools.
