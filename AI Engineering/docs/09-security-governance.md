# 09 — Security, PII Safety, Auditability & Governance

> **Goal:** Make the system **enterprise-safe**: enforce who-can-see-what, protect PII,
> log everything for audit, and meet governance/compliance requirements. In the
> enterprise, this is not optional polish — it's the gate to going live.

---

## 1. The threat model for LLM systems

LLM systems add attack surfaces traditional apps don't have:

| Threat | Example | Defense |
|--------|---------|---------|
| **Cross-tenant leakage** | tenant A's data in tenant B's answer | server-enforced tenant filter (T03/T05) |
| **Broken access control** | user sees a doc they can't open in source | ACL-filtered retrieval (§3) |
| **Prompt injection** | doc/tool text overrides instructions | input + content screening (T06 §2) |
| **PII exposure** | SSN echoed into an answer or a log | redaction at ingest + output (§4) |
| **Excessive agency** | agent deletes data / sends email | least-privilege tools + approval (T04) |
| **Sensitive data to 3rd-party LLM** | regulated data leaves the boundary | redaction / on-prem model / DPA (§4,§7) |
| **Insecure output** | model returns runnable SQL/script that's executed | validate/sandbox outputs (T08 §5) |

Map your controls to a framework — **OWASP Top 10 for LLM Applications** is the
practical reference; **NIST AI RMF** and **ISO/IEC 42001** frame governance.

---

## 2. Authentication & authorization

```
 request ──► AuthN (who are you?) ──► AuthZ (what can you see/do?) ──► tenant + ACL filter ──► RAG/agent
              JWT/OIDC                  roles, groups, scopes            applied at EVERY data access
```

```python
@dataclass
class Principal:
    user_id: str
    tenant_id: str            # derived from token — NEVER from request body
    groups: list[str]         # e.g. ["group:hr", "group:all-staff"]
    scopes: list[str]         # e.g. ["kb:read", "crm:read"] — NOT "crm:write"
    pii_clearance: bool

async def verify_jwt(authorization: str) -> Principal:
    claims = decode_and_verify(authorization)     # validate signature, issuer, expiry
    return Principal(user_id=claims["sub"], tenant_id=claims["tenant"],
                     groups=claims["groups"], scopes=claims["scopes"],
                     pii_clearance="pii:read" in claims["scopes"])
```

Principles: **identity drives everything** (tenant + ACL come from the verified token,
never the client payload); **least privilege** (agents/tools get the narrowest scope that
works — a read-only KB agent has no write scopes); **short-lived tokens**, validated on
every request.

---

## 3. Access control in retrieval (the part demos skip)

The #1 enterprise RAG failure: indexing everything, then answering from documents the
user can't actually open. **Retrieval must honor source-system permissions.**

```python
def authorized_filter(principal: Principal) -> dict:
    return {
        "tenant_id": principal.tenant_id,          # hard tenant boundary
        "acl": {"any": principal.groups},          # chunk-level ACL match (from T08 connectors)
    }

# Applied to EVERY retrieval, graph traversal, and tool call — centralized, never inline-skipped
chunks = hybrid_retrieve(query, filters=authorized_filter(principal))
```

Make it impossible to forget:
- **Capture ACLs at ingest** from the source system (T08) and store on every chunk/node (T01/T05).
- **Centralize the filter** in one retrieval function so no code path can omit it.
- **Default-deny:** a chunk with no ACL is private, not public.
- **Test it:** the cross-tenant + cross-ACL isolation eval (T06 §5) runs in CI — seed
  restricted data, query as an unauthorized user, assert zero leakage.
- **Re-check on read:** for highly sensitive data, verify live permission at answer time
  (permissions revoked since last sync shouldn't leak through a stale index).

---

## 4. PII safety

### 4.1 Detect & redact at ingest and at output

Use **Microsoft Presidio** (or cloud DLP) to detect and anonymize PII — at ingest before
storage/embedding, and at output before returning/logging.

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

analyzer, anonymizer = AnalyzerEngine(), AnonymizerEngine()

def redact_pii(text: str, allow: bool = False) -> str:
    if allow:                                       # cleared user → return as-is
        return text
    results = analyzer.analyze(text=text, language="en",
                               entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
                                         "CREDIT_CARD", "US_SSN", "IBAN_CODE"])
    return anonymizer.anonymize(text=text, analyzer_results=results).text   # → <PERSON>, <US_SSN>
```

Where PII handling must happen:
- **At ingest:** redact or tag PII before embedding/storing. Tagging (vs hard-removal)
  lets cleared users still retrieve it while others get masked versions.
- **Before sending to a third-party LLM:** if regulated data can't leave your boundary,
  redact it from the prompt (and re-insert on the way back if needed), or use an on-prem
  model (§7).
- **At output:** redact before returning *and before logging* — PII in logs is a common,
  silent breach.
- **Reversible tokenization** when you need to round-trip: replace PII with tokens,
  process, then de-tokenize for cleared recipients.

### 4.2 Data minimization & retention

Only ingest what you need; set **retention/TTL** on chunks, caches, and logs; honor
**deletion/right-to-erasure** requests by deleting from source → index → graph → caches →
logs (track lineage so you *can*).

---

## 5. Auditability

If you can't reconstruct *who asked what, what was retrieved, what was sent to the model,
and what came back*, you can't pass an enterprise audit. Log it all — immutably.

```python
async def audit_log(event: dict):
    record = {
        "ts": now_iso(), "request_id": event["request_id"],
        "user_id": event["principal"].user_id, "tenant_id": event["principal"].tenant_id,
        "action": event["action"],                         # "ask", "ingest", "tool:create_case"
        "query": event.get("query"),
        "retrieved_doc_ids": event.get("doc_ids"),         # provenance of the answer
        "tools_called": event.get("tools"),
        "model": event.get("model"), "tokens": event.get("tokens"),
        "guard_verdicts": event.get("guards"),             # what was blocked/redacted (T06)
        "decision": event.get("decision"),                 # answered / refused / escalated
    }
    await append_only_store.write(record)                  # tamper-evident / WORM
```

Audit must be: **immutable** (append-only/WORM, no edits), **complete** (every
AI-influenced decision, including refusals and redactions), **attributable** (user +
tenant + request id on every record), and **retained** per your compliance window. These
logs also feed online evals and incident forensics.

---

## 6. Governance & lifecycle

Governance is the organizational wrapper that keeps the system compliant over time:

- **Model & prompt registry:** version models, prompts, and configs; know exactly what
  was in production when an output was produced.
- **Change control + eval gates:** every prompt/model/retrieval change passes the eval
  suite (T06) and is reviewed before deploy — no silent prod changes.
- **Human-in-the-loop** on high-impact actions and decisions (T04 §7.2).
- **Cost governance:** per-tenant budgets, token quotas, alerts; model tiering (T04 §9).
- **Documentation:** data flow diagrams, DPIAs, model cards, and a clear statement of
  what data goes where — what auditors and security teams will ask for.
- **Roles & ownership:** SMEs own domain correctness, security owns controls, you own the
  pipeline — define who signs off on what.

### Compliance landscape (know which apply to you)

| Regime | Relevance |
|--------|-----------|
| **GDPR / CCPA** | PII handling, consent, erasure, data residency |
| **HIPAA** | health data — usually demands on-prem/BAA-covered models |
| **SOC 2 / ISO 27001** | security controls, audit evidence |
| **EU AI Act** | risk classification, transparency, human oversight |
| **ISO/IEC 42001** | AI management system governance |

Bring security/compliance in **early** — retrofitting tenant isolation, PII redaction, and
audit into a live system is far costlier than designing them in.

---

## 7. Deployment & data-boundary choices

Where the model runs determines what data can touch it:

| Option | Data boundary | Use when |
|--------|---------------|----------|
| **Hosted API** (Claude, etc.) with DPA / zero-retention | leaves network, contractually protected | most enterprise, non-extreme sensitivity |
| **VPC / private endpoint** (e.g. Bedrock, Azure) | within cloud tenancy | regulated, want managed model |
| **On-prem / self-hosted** (vLLM + open weights) | never leaves network | strict data residency (HIPAA, classified) |

Also: **encrypt** in transit (TLS) and at rest (KMS-managed keys); network-isolate the
vector DB/graph (no public exposure); **secrets in a vault** with rotation; verify the
provider's **data-retention / training-use** terms (confirm zero-retention / no-train for
your account). Don't assume — get it in the contract.

---

## 8. Checklist

- [ ] AuthN (validated JWT/OIDC) + AuthZ (roles/scopes); tenant + ACL from token, never client.
- [ ] ACL-filtered retrieval on every access; centralized filter; default-deny; CI isolation eval.
- [ ] PII detection/redaction at ingest, before 3rd-party LLM, at output, and before logging.
- [ ] Data minimization, retention/TTL, and working erasure across index/graph/cache/logs.
- [ ] Immutable, complete, attributable audit log of every AI decision (incl. refusals/redactions).
- [ ] Model/prompt registry, eval-gated change control, human-in-the-loop, cost governance.
- [ ] Map controls to OWASP-LLM / NIST AI RMF; know which regimes (GDPR/HIPAA/AI Act) apply.
- [ ] Choose data boundary (hosted+DPA / VPC / on-prem) by sensitivity; encrypt; vault secrets.

---

## You've completed the series

You now have an end-to-end blueprint:

**[01](01-rag-pipelines.md)** retrieval quality → **[02](02-document-ingestion.md)** clean
ingestion → **[03](03-vector-search.md)** scalable vector search → **[04](04-langgraph-agents.md)**
agentic orchestration → **[05](05-knowledge-layers.md)** structured knowledge →
**[06](06-guardrails-evals.md)** trust & measurement → **[07](07-fastapi-microservices.md)**
serving → **[08](08-enterprise-integration.md)** integration → **[09]** security & governance.

The throughline: **invest in retrieval and ingestion, enforce tenancy and ACLs at every
layer, measure everything with evals, and never let an AI system take a consequential
action without bounds, approval, and an audit trail.**
