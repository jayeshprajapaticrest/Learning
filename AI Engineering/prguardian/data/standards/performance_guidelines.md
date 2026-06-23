# Performance Engineering Standards

## Database access
- No queries inside loops (N+1). Batch with `IN (...)` or a join.
- Every list/collection endpoint MUST paginate and enforce a maximum page size.

## Caching
- Caches MUST have a bounded size and a TTL. An unbounded in-process cache is a
  HIGH finding (memory growth / stale data).
- Cache keys must include every input that changes the result.

## Hot paths
- No blocking/synchronous I/O on request hot paths in async code.
