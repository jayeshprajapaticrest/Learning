# Module 8 — Evaluation & Observability

> **The most important module in this repo.** Build this *before* you optimize anything. "You cannot improve what you cannot measure" is not a cliché in RAG — it is the difference between engineering and guessing. Every other module's "measure the lift on your eval set" instruction depends on what you build here.

---

## 1. Why it matters

RAG has a long pipeline (chunk → retrieve → rerank → assemble → generate), and a quality problem can originate at any stage. Without measurement you:

- **Tune by vibes** — change something, eyeball a few queries, convince yourself it's better. It usually isn't, and you can't tell.
- **Can't localize failures** — is the answer wrong because retrieval missed the doc, the reranker buried it, the context order hid it, or the model ignored it? Each has a different fix.
- **Can't ship safely** — no regression gate means every change risks silent degradation.
- **Can't justify cost** — no way to argue a reranker or GraphRAG is worth its price.

Evaluation gives you a **scoreboard**; observability gives you **production truth** (real queries, real failures, latency, cost) that feeds back into the scoreboard.

---

## 2. Core concepts

### Two halves of the pipeline → two kinds of metrics

**A. Retrieval metrics (IR)** — did we fetch the right evidence? Computed against labeled relevant docs.
- **Recall@k** — fraction of relevant docs retrieved in top-k. *The most important RAG retrieval metric* (if it's not retrieved, it can't be used).
- **Precision@k**, **MRR** (mean reciprocal rank — position of first relevant), **nDCG@k** (graded relevance, position-discounted — the gold-standard ranking metric), **Hit Rate / Context Recall**, **MAP**.

**B. Generation / end-to-end metrics** — given the context, was the answer good? Mostly LLM-as-judge or reference-based.
- **Faithfulness / groundedness** — is every claim supported by the retrieved context? (Anti-hallucination metric.)
- **Answer relevance** — does the answer address the question?
- **Context precision / context recall** (RAGAS) — is the retrieved context relevant, and does it contain the ground-truth answer?
- **Correctness** — vs. a reference answer (LLM-judge or exact/semantic match).
- **Answer completeness, citation accuracy, refusal correctness** (did it correctly say "I don't know"?).

### The RAGAS framework
**RAGAS** (Es et al., 2023, arXiv:2309.15217; docs: <https://docs.ragas.io>) operationalizes faithfulness, answer relevance, context precision, and context recall — many computable *reference-free* via LLM-as-judge. The standard starting point for RAG-specific eval.

### LLM-as-a-judge (use carefully)
LLM grading scales eval cheaply but has known biases (position, verbosity, self-preference). Primary source: **"Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"** (Zheng et al., 2023, arXiv:2306.05685). Mitigate with: clear rubrics, reference answers, randomized positions, pairwise comparison, and **human-calibration** of the judge on a sample.

### Golden datasets
The foundation of all eval. A set of representative (query, ideal answer, relevant doc IDs) examples. Build from: real/expected user questions, SME-authored Q&A, and **synthetic generation** (LLM generates Q/A from your docs — RAGAS and LlamaIndex have generators) followed by **human review**. Cover easy, hard, multi-hop, adversarial, and "should-refuse" cases. Version it; grow it from production failures.

### Benchmarks (for calibration / research)
**BEIR** (zero-shot retrieval, arXiv:2104.08663), **MTEB** (embeddings, arXiv:2210.07316), **MS MARCO**, **Natural Questions**, **HotpotQA** (multi-hop), **RGB / CRAG / RAG benchmarks**. Useful for component selection; **your own golden set is the source of truth for your app.**

---

## 3. Observability (production truth)

Tracing and monitoring the live system. What to capture per request:
- **Full trace/span tree:** query → (rewrite) → retrieved doc IDs + scores → reranked set → assembled context → prompt → model + version → output → post-checks. Use **OpenTelemetry GenAI semantic conventions** as the standard.
- **Quality signals:** online faithfulness/relevance scoring (sampled), user feedback (👍/👎), refusal/abstention rate, citation validity.
- **Operational signals:** latency per stage (retrieval, rerank, generation, TTFT), token usage & cost per request, error rates, cache hit rates.
- **Drift:** embedding/query distribution drift, retrieval score distributions over time.

Tools (official): **LangSmith**, **Arize Phoenix** (OSS), **Langfuse** (OSS), **TruLens**, **OpenLLMetry/OpenLLMetry**, plus your normal metrics/log stack (Prometheus/Grafana, OpenTelemetry collectors).

### Closing the loop
Production traces + user feedback → mine failures → add them to the golden set → re-run offline eval → fix → gate in CI. This feedback loop is what makes a RAG system *improve* over time rather than rot.

---

## 4. Learning path

### Beginner
- Build a 50–100 example golden set (mix hand-written + synthetic + reviewed).
- Compute **recall@k, MRR, nDCG** on retrieval. Run **RAGAS** for faithfulness/answer-relevance/context metrics. Establish a **baseline scoreboard**.

### Intermediate
- Add **LLM-as-judge correctness** with a rubric; calibrate it against ~30 human labels.
- Wire eval into **CI** as a regression gate (fail the build if faithfulness/recall drops > threshold).
- Add **tracing** (LangSmith/Phoenix/Langfuse) in dev.

### Advanced
- **Component-level eval:** isolate and A/B each stage (chunking, embedding model, reranker, k, prompt) against the scoreboard.
- Build **production observability**: per-stage latency/cost dashboards, online sampled quality scoring, feedback capture, drift monitors.
- Generate larger synthetic eval sets with difficulty stratification; detect and fix judge bias.

### Expert
- Build **eval-as-a-service**: shared golden-dataset governance, standardized metrics, dashboards other teams reuse; an internal RAG benchmark.
- Automate the **trace → failure-mining → golden-set → CI** loop. Add canary/shadow deployments with online eval before full rollout.
- Statistical rigor: confidence intervals, significance tests on metric deltas (avoid celebrating noise).

---

## 5. Best resources

- **Papers:** RAGAS (2309.15217); LLM-as-judge / MT-Bench (2306.05685); ARES automated RAG eval (Saad-Falcon et al., 2023, arXiv:2311.09476); BEIR (2104.08663); MTEB (2210.07316).
- **Docs:** RAGAS docs (<https://docs.ragas.io>); Arize Phoenix docs; LangSmith eval docs; Langfuse docs; TruLens docs; DeepEval docs; OpenTelemetry **GenAI semantic conventions**.
- **Blogs:** Arize, LangChain (eval), Pinecone eval guides; *Introduction to Information Retrieval* (Manning et al.) chapter on evaluation (recall/precision/MAP/nDCG fundamentals).
- **Repos:** `explodinggradients/ragas`, `Arize-ai/phoenix`, `langfuse/langfuse`, `confident-ai/deepeval`, `truera/trulens`, `beir-cellar/beir`.

---

## 6. Production architecture patterns

- **Offline eval harness** (golden set + metrics) runnable locally and in CI; results stored/versioned for trend lines.
- **CI quality gate:** PRs that change the pipeline run eval; merge blocked on regression beyond thresholds.
- **Tracing-first serving:** every request emits a structured trace (OTel) to an observability backend.
- **Sampled online scoring** + **feedback widget** → labeled data lake → periodic golden-set refresh.
- **Shadow/canary deploys** with side-by-side eval before promoting changes.

---

## 7. Common mistakes & anti-patterns

- **No eval set at all** (the cardinal sin). Tuning by anecdote.
- **Only end-to-end metrics, no retrieval metrics** → can't localize whether retrieval or generation failed.
- **Trusting LLM-judge blindly** without human calibration or bias controls.
- **Tiny/unrepresentative golden set** missing hard, multi-hop, adversarial, and refusal cases.
- **Eval set leakage** (examples drawn from the same text the model memorized; or tuning on the test set).
- **Celebrating noise** — declaring a 1% win on 20 examples without significance.
- **No production observability** → blind to real-world failures, latency, and cost.
- **Never updating the golden set** from production failures → eval drifts away from reality.

---

## 8. Interview-level expectations

- Define recall@k, precision@k, MRR, nDCG and **when nDCG is preferred** (graded, position-aware).
- Explain RAGAS metrics (faithfulness, answer relevance, context precision/recall) and what each catches.
- Explain LLM-as-judge, its biases, and how to mitigate them.
- Describe how you'd **localize** a RAG failure to a specific stage using component-level eval.
- Describe a production observability setup and the trace→golden-set feedback loop.
- Explain why you build eval **before** optimizing.

---

## 9. Enterprise-scale considerations

- **Governance of golden datasets:** ownership, versioning, PII handling, SME sign-off, drift review cadence.
- **Cost of eval:** LLM-judge over large sets is expensive; sample, cache, and use cheaper judge models where calibrated.
- **Compliance:** auditable answer quality, citation accuracy, and abstention behavior may be regulatory requirements.
- **Multi-tenant eval:** per-tenant quality SLOs and leakage tests (adversarial cross-tenant queries).
- **Continuous monitoring** for quality/latency/cost regressions tied to alerting.

---

## 10. Trade-offs & decision framework

```
What failed? → run RETRIEVAL metrics first.
   Low recall@k?         → fix chunking / hybrid / embeddings / k (Modules 2,3).
   Good recall, bad rank? → fix reranking / ordering (Modules 4,7).
   Good context, bad answer? → fix prompt/grounding/model (Module 7).

Reference answers available? → correctness + context-recall.
Reference-free needed?       → RAGAS faithfulness/relevance + context-precision.
Need scale + cheap?          → LLM-judge (calibrated). Need ground truth? → human + small sample.

Ship gate: block on regression in (recall@k, faithfulness, correctness) beyond threshold, with significance.
```

---

## 11. Real-world use cases

- **CI quality gates** preventing silent RAG regressions (standard at mature AI orgs).
- **Component selection** — choosing embedding model / reranker / chunking by measured lift, not hype.
- **Production monitoring** — catching retrieval drift, rising hallucination, latency/cost creep.
- **Vendor/model evaluation** — objective bake-offs (e.g., embedding or reranker providers) on your own benchmark.

---

## 12. Essential vs optional

- **Essential:** golden dataset; retrieval metrics (recall@k, nDCG, MRR); RAGAS faithfulness/answer-relevance/context metrics; basic tracing; a baseline scoreboard.
- **High-ROI:** CI eval gate; production observability (latency/cost/quality); calibrated LLM-judge; feedback loop into the golden set.
- **Optional / situational:** custom internal benchmarks, shadow/canary online eval, statistical significance tooling — at scale / platform maturity.

---

### Capstone project for this module
Build a reusable eval harness: a versioned golden set, retrieval metrics + RAGAS + a calibrated LLM-judge, a one-command run that prints a scoreboard, and a CI job that fails on regression. Then retro-fit it to Modules 2–7 and reproduce every "measure the lift" claim with real numbers from *your* data. This harness is the backbone of everything else you build.
