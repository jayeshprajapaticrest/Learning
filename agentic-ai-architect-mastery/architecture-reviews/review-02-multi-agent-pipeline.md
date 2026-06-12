# Architecture Review 2 — Multi-Agent Document Processing Pipeline

> **Difficulty:** Principal Engineer | **Related Modules:** 09, 10, 11, 13, 15, 19

---

## Instructions

You are reviewing a multi-agent document processing pipeline design before the team commits to a 3-month implementation. Your task:

1. Read the design carefully
2. Identify **all architectural flaws** (there are exactly **9 seeded flaws**)
3. For each flaw: state the flaw, explain the risk, and propose a fix
4. Compare your findings to the model answer at the bottom

---

## Design Document Under Review

### System Overview

A law firm processes 500+ contracts per day. The pipeline: ingests PDFs, extracts key clauses, classifies risk, generates a summary, and stores results in a document management system. The pipeline is fully automated with no human review step (human review happens downstream by a paralegal).

### Architecture Diagram

```
PDF Upload → Ingestion Agent → Extraction Agent → Classification Agent
                                                        ↓
                            Summary Agent ←─────── Risk Agent
                                 ↓
                         Storage Agent → Document Management System
```

### Agents

**1. Ingestion Agent**
- Converts PDF to text using pdfplumber
- Extracts metadata (filename, upload timestamp, file size)
- Passes text to Extraction Agent via shared Redis key

**2. Extraction Agent**
- Receives full contract text (may be 50+ pages)
- Extracts: parties, dates, key clauses (payment terms, termination, liability, IP ownership)
- Outputs: JSON with extracted fields
- Model: `claude-haiku-4-5`

**3. Classification Agent**
- Input: extracted clauses JSON
- Classifies risk level: Low / Medium / High
- Rule: if liability clause > $1M OR termination is unilateral → High risk
- Model: `claude-haiku-4-5`

**4. Risk Agent**
- Receives raw contract text + classification
- Produces: risk narrative, flags, recommendations
- Model: `claude-opus-4-8`

**5. Summary Agent**
- Receives raw contract text + risk narrative + extracted clauses
- Produces: 2-page executive summary
- Model: `claude-sonnet-4-6`

**6. Storage Agent**
- Receives summary + risk rating + extracted JSON
- Calls DMS API to store document with metadata
- Also stores to Postgres for search

### Agent Communication

All agents share state via Redis keys:
- `doc:{doc_id}:raw_text` — raw contract text from ingestion
- `doc:{doc_id}:extracted` — extracted clauses JSON
- `doc:{doc_id}:risk_classification` — High/Medium/Low
- `doc:{doc_id}:risk_narrative` — full risk narrative
- `doc:{doc_id}:summary` — executive summary

Pipeline coordination: each agent polls Redis for its input key to appear (polling every 500ms).

### Error Handling

```python
def run_agent_step(agent_fn, input_key, output_key, doc_id):
    while True:
        value = redis.get(input_key)
        if value:
            result = agent_fn(value)
            redis.set(output_key, result)
            return
        time.sleep(0.5)
```

### Concurrency

- Each document is processed sequentially through all 6 agents
- System processes 10 documents simultaneously (10 parallel pipelines)
- Worker pool: 10 threads, one per document

### Context Management

- Full contract text is passed to Extraction Agent, Risk Agent, and Summary Agent
- No chunking — contracts are included whole in the context
- Average contract: 15,000 tokens; some contracts: up to 80,000 tokens
- System prompt: 2,000 tokens fixed

### Evaluation and Testing

- No automated eval
- Integration test: process 3 sample contracts, manually verify output
- QA: paralegal spot-checks 1% of processed documents

### Deployment

- All 6 agents run as functions in a single Python process
- Deployed on a single EC2 instance (c5.4xlarge, 16 CPUs)
- No retry logic — if any step fails, the whole document is abandoned
- Redis runs on the same EC2 instance as the agents

### Cost Design

- Model selection: Haiku for extraction/classification, Sonnet for summary, Opus for risk
- No caching implemented
- No per-document cost tracking
- Daily estimated cost: not calculated

---

## Your Task

Find and document all 9 architectural flaws. For each flaw:
- **What is the flaw?**
- **What is the risk?**
- **How would you fix it?**

---

---

---

*(Model answer below — do not read until you have found all 9 flaws)*

---

---

---

## Model Answer

### Flaw 1: Full contract text passed to 3 separate agents — O(n) context duplication with no chunking

**What:** The raw contract text (15K–80K tokens) is passed in full to the Extraction Agent, Risk Agent, and Summary Agent. For an 80K-token contract, that's 240K input tokens across 3 agents just for the raw text, plus the already-extracted output being passed onward.

**Risk:**
1. Contracts > 180K tokens will exceed `claude-opus-4-8`'s context window
2. Cost is superlinear: a 5× larger contract costs > 5× more (all three agents get the full text)
3. Quality degrades on very long contracts as the model attends to more irrelevant context

**Fix:**
1. Hierarchical chunking: split contract into sections; Extraction Agent processes each section independently; merge results
2. Pass only relevant sections to each downstream agent (Risk Agent gets liability/termination clauses, not the entire contract)
3. Prompt caching: the contract text is static within a pipeline run — cache it to reduce cost on repeated passes
4. Extraction Agent output should be sufficient for Classification and Risk; they shouldn't need raw text

---

### Flaw 2: Polling loop with `time.sleep(0.5)` — unbounded blocking with no timeout

**What:** `run_agent_step` loops indefinitely polling Redis every 500ms. If the upstream agent fails silently (crashes without writing the output key), this loop never terminates.

**Risk:**
1. Zombie threads: worker threads can be stuck indefinitely on abandoned documents
2. Resource exhaustion: 10 threads all stuck means no throughput for new documents
3. No observability: there is no timeout, no alert, no way to detect the hang

**Fix:**
1. Add timeout: if input key doesn't appear within N seconds, raise a timeout error
2. Use Redis pub/sub or Kafka for event-driven handoffs instead of polling
3. Use a proper orchestration framework (LangGraph, Temporal) with explicit step timeouts and retry policies
4. Dead letter queue: failed/timed-out documents go to a DLQ for manual review

---

### Flaw 3: No retry logic — any step failure abandons the document silently

**What:** "If any step fails, the whole document is abandoned." There is no retry, no dead letter queue, no alert.

**Risk:**
1. At 500 documents/day with even a 1% transient failure rate (network, rate limits, provider issues), 5 documents per day are silently dropped
2. No visibility into which documents failed or why
3. Transient errors (rate limits, provider timeouts) are treated the same as permanent failures

**Fix:**
1. Retry with exponential backoff for transient errors (rate limits: 60s initial wait)
2. Dead letter queue for permanently failed documents
3. Alert on DLQ depth > threshold
4. Checkpoint completed steps: if extraction succeeds but classification fails, retry only from classification
5. Track failure reason per document in Postgres

---

### Flaw 4: Redis and all agents on the same EC2 instance — SPOF with no HA

**What:** Single EC2 instance hosts Redis + all 6 agent functions. Redis is not persisted (no AOF/RDB configured).

**Risk:**
1. Single point of failure: EC2 instance failure drops all in-flight documents and all state
2. Redis restart (including EC2 stop/start) loses all `doc:{doc_id}:*` keys — all in-flight documents are lost, with no recovery path
3. CPU contention: 10 parallel pipelines + Redis on 16 CPUs will saturate at peak

**Fix:**
1. Use managed Redis (ElastiCache) with multi-AZ replication and AOF persistence
2. Use Postgres (not Redis) as the durable state store for document processing state; Redis is cache only
3. Distribute workers across multiple instances or use container orchestration (ECS/k8s)
4. Checkpointing: write step results to Postgres immediately; Redis is a cache, not the source of truth

---

### Flaw 5: Classification Agent uses Haiku for a high-stakes legal risk decision

**What:** The Classification Agent uses `claude-haiku-4-5` to decide if a legal contract is High/Medium/Low risk. This decision drives downstream handling and is seen by paralegals.

**Risk:**
1. Haiku is optimized for speed/cost, not nuanced legal reasoning
2. A misclassification (High → Low) means a risky contract doesn't get flagged
3. In legal contexts, the cost of a false negative (missed risk) far exceeds the savings from a cheaper model

**Fix:**
1. Use `claude-sonnet-4-6` or higher for risk classification
2. Add confidence scoring: if confidence < 0.8, always escalate to human review
3. Add a validation step: LLM-as-judge that checks the risk classification against the extracted clauses
4. The cost difference between Haiku and Sonnet for a single classification is < $0.001 — immaterial for a law firm

---

### Flaw 6: No audit trail — no record of which model version produced which output

**What:** There is no logging of model version, system prompt version, or agent configuration used to produce each document's output.

**Risk:**
1. If a model is deprecated or the system prompt changes, there is no way to identify which documents were processed with which configuration
2. Legal liability: a law firm must be able to demonstrate the process used to produce a document summary
3. Debugging: if a classification error is discovered later, there is no way to trace it back to the model version

**Fix:**
1. Version bundle (Module 15): record `{model_id, system_prompt_hash, tool_version}` with every document processing record
2. Postgres table: `document_processing_log(doc_id, step, model, prompt_hash, input_tokens, output_tokens, duration_ms, created_at)`
3. Immutable: log records are never updated; errors are logged as new records

---

### Flaw 7: No cost tracking — daily cost unknown

**What:** "Daily estimated cost: not calculated." No per-document cost tracking.

**Risk:**
1. Unexpected bills: at 500 docs/day with Opus for risk analysis (~$0.10-0.50/doc), monthly cost could be $15K-$75K
2. No alerting if cost spikes (model update causes more verbose output → more tokens)
3. Cannot charge clients per-document (which law firms often need to do)

**Fix:**
1. Track input/output tokens per step per document in Postgres
2. Calculate per-document cost using current model pricing
3. Daily cost dashboard; alert if daily cost exceeds budget
4. Estimated cost at 500 docs/day with current model mix (calculate it and document it)

---

### Flaw 8: Extraction Agent output trusted without validation — garbage propagates downstream

**What:** The Extraction Agent's JSON output is passed directly to Classification, Risk, and Summary agents without validation.

**Risk:**
1. Hallucinated clause extractions (e.g., "$5M liability" when the contract says "$500K") propagate through all downstream agents
2. Malformed JSON causes downstream agents to fail with unparseable input
3. Missing required fields (e.g., no termination clause found) not handled — classification logic breaks

**Fix:**
1. Validate Extraction Agent output against a Pydantic schema before passing downstream
2. Confidence scores on extracted fields: low-confidence extractions flagged for human review
3. Cross-validate critical fields: if liability amount is extracted, verify it appears in the raw text
4. If validation fails: route to human review, not silent failure

---

### Flaw 9: No integration with human-in-the-loop for high-risk documents

**What:** The pipeline is "fully automated with no human review step." Paralegals review documents "downstream" — implying after the document is already stored in the DMS.

**Risk:**
1. For a law firm, High-risk contracts should be reviewed by a human before being stored as "processed" — the storage is the action that matters
2. If the Summary Agent produces a misleading summary and a paralegal relies on it without re-reading, legal exposure follows
3. "Human review happens downstream" is too late if the summary/risk rating has already been acted on

**Fix:**
1. High-risk documents: pause pipeline after Classification, create a human review task, resume only after approval
2. Summary documents should include a prominent disclaimer: "AI-generated summary. Reviewed by: [paralegal name/date]"
3. Confidence threshold: if risk classification confidence < 0.85 for any category, mandatory human review
4. Audit log should capture human review outcome and reviewer identity

---

## Scoring Guide

| Flaws Found | Assessment |
|-------------|------------|
| 8-9 | Principal/Architect: systemic thinking across reliability, cost, legal risk |
| 6-7 | Staff level: caught infrastructure + cost + reliability |
| 4-5 | Senior level: caught the most visible issues |
| 1-3 | Needs more production systems + multi-agent experience |

The hardest flaws to spot are typically: Flaw 1 (context duplication cost model), Flaw 6 (audit trail as legal requirement), and Flaw 9 (HITL placement — paralegals reviewing after storage is too late). These require understanding the business domain (law firm), not just the technical architecture.
