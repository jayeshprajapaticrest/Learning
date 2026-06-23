# INC-2024-11 — Out-of-memory from unbounded cache

**Severity:** SEV-2
**Root cause:** A product-catalog cache was added as a plain module-level dict
with no size limit and no TTL. Under traffic it grew until the service hit OOM
and restarted in a loop.

**Fix:** Replaced with an LRU cache bounded to 10k entries and a 5-minute TTL.

**Lesson:** Every cache must have a bounded size and a TTL. Unbounded
in-process caches are a recurring source of memory incidents.
