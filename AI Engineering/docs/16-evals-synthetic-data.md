# 16 — Eval Frameworks & Synthetic Data Generation

> LLM-Ops part 2. You can't improve what you don't measure. This covers **how to evaluate
> RAG and agents** (metrics, frameworks, harness, CI) and **how to generate synthetic
> data** to build eval sets and training data fast. Builds on [T06](06-guardrails-evals.md).

---

## Part A — Eval Frameworks

### 1. Why evals are the core LLM-Ops practice

LLM systems are non-deterministic and fail silently. Without evals, every prompt/model/
chunking/retrieval change is a gamble — you can't tell improvement from regression. Evals
convert "feels better" into a **number you can gate deploys on**. Build the harness early;
it's the flywheel for all quality work.

```
 change (prompt/model/retrieval) → run eval suite → compare to baseline → gate deploy
                                          ▲                                     │
                                          └──────── mine prod failures ◄────────┘
```

### 2. The two layers of RAG metrics

Evaluate retrieval and generation **separately** — a bad answer could be either a
retrieval miss or a generation fault, and you must know which.

**Retrieval metrics** (is the right context found? — the *ceiling* on quality):

| Metric | Meaning |
|--------|---------|
| **Recall@k** | fraction of relevant docs in top-k |
| **Precision@k** | fraction of top-k that are relevant |
| **MRR** | mean reciprocal rank of the first relevant doc |
| **NDCG** | rank-quality with graded relevance |
| **Context recall / precision** | did retrieved context cover / avoid noise vs ground truth |

**Generation metrics** (is the answer good?):

| Metric | Meaning |
|--------|---------|
| **Faithfulness / groundedness** | every claim supported by context (hallucination check) |
| **Answer relevancy** | does it address the question |
| **Correctness** | matches the reference answer |
| **Completeness** | covers all parts of the question |

### 3. Agent-specific metrics

Agents add dimensions beyond answer quality:

- **Task success / goal completion** — did it achieve the objective (end-to-end)?
- **Tool-selection accuracy** — right tool, right time?
- **Tool-argument correctness** — valid, correct parameters?
- **Trajectory quality** — efficient path, no needless loops?
- **Step count / cost / latency** — efficiency budgets.
- **Recovery** — did it self-heal from a tool error ([T04 §6](04-langgraph-agents.md))?

Evaluate both the **final outcome** and the **trajectory** (the sequence of steps) — an
agent can get the right answer via a wrong, expensive path.

### 4. Frameworks (pick one, integrate it)

| Framework | Strengths |
|-----------|-----------|
| **RAGAS** | RAG-specific metrics (faithfulness, relevancy, context precision/recall), synthetic test-set generation |
| **LangSmith** | datasets, LLM-judge evaluators, tracing, CI integration, regression tracking |
| **DeepEval** | pytest-style assertions for LLM outputs; many metrics; CI-friendly |
| **TruLens** | feedback functions, "RAG triad", observability |
| **promptfoo** | config-driven prompt/model comparison + red-teaming |
| **Phoenix (Arize)** | tracing + eval, drift monitoring |

```python
# RAGAS
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
scores = evaluate(dataset, metrics=[faithfulness, answer_relevancy,
                                    context_precision, context_recall])
```

### 5. LLM-as-judge (when there's no single right string)

Most generation quality is graded by a strong LLM against a rubric + reference:

```python
JUDGE = """Question: {q}
Reference answer: {ref}
Candidate: {cand}

Score 1-5 for correctness and faithfulness. Penalize unsupported claims.
Return JSON: {{"correctness": n, "faithfulness": n, "reasoning": "..."}}."""
```

Judge hygiene (or your numbers lie):
- **Strong judge model**, clear **rubric**, and a **reference** answer where possible.
- **Mitigate bias** — randomize answer order (position bias), cap length (verbosity bias).
- **Calibrate against humans** — periodically check judge vs human labels on a sample.
- **Prefer pairwise** ("A vs B, which is better?") for comparing two systems — often more
  reliable than absolute 1–5 scores.

### 6. The golden dataset

50–300 examples of `(input, ideal_output, relevant_context_ids, metadata)`:
- Sourced from **real production traffic** + edge cases + known failures.
- **Versioned in git**; every new bug becomes a new test case (the set grows weekly).
- Includes **adversarial** (injection) and **out-of-scope** ("should refuse") cases.
- Stratified across query types, tenants, doc types so aggregate scores aren't misleading.

### 7. The eval harness in CI

```python
THRESHOLDS = {"faithfulness": 0.90, "answer_relevancy": 0.85, "recall@10": 0.80,
              "task_success": 0.85}

def gate(scores: dict, baseline: dict) -> int:
    regressions = {m: (scores[m], baseline.get(m)) for m in scores
                   if scores[m] < THRESHOLDS.get(m, 0)
                   or (m in baseline and scores[m] < baseline[m] - 0.03)}  # 3% regression band
    if regressions:
        print("EVAL FAIL:", regressions); return 1
    return 0
```

Run on every prompt/model/retrieval change; **block the deploy on regression**. Compare to
the previous version, not just absolute thresholds, to catch quiet drops.

### 8. Online / production evaluation

Offline ≠ production. Also:
- **Log every interaction** (query, retrieved ids, answer, latency, cost, guard verdicts) — trace it.
- **User feedback** (👍/👎, edits, escalations) sampled for review.
- **Async judges** on a traffic sample for faithfulness/quality drift.
- **Drift monitors** — new query patterns, new doc types, model-version changes.
- **Failure mining** → new golden cases → fix → re-eval. This loop is the engine of quality.

---

## Part B — Synthetic Data Generation

### 9. Why synthetic data

Hand-labeling eval/training data is slow and scarce. **LLMs generate it cheaply** — to:
- **Bootstrap eval sets** before you have production traffic.
- **Cover edge cases** real traffic hasn't hit yet.
- **Create training data** for fine-tuning smaller models / rerankers / classifiers.
- **Red-team** with adversarial inputs (injection, jailbreaks, PII bait).

### 10. Generating a RAG eval set from your own corpus

The key insight: **you already have the answers — your documents.** Generate questions
*from* chunks so you get `(question, answer, source)` triples with ground truth for free.

```python
QGEN = """From the passage below, write {n} diverse questions a user might ask that this
passage fully answers. For each, give the exact answer and quote the supporting sentence.
Return JSON: [{{"question": "...", "answer": "...", "evidence": "..."}}]

<passage>{chunk}</passage>"""

def make_eval_set(chunks, n=2):
    rows = []
    for c in chunks:
        for qa in json.loads(llm.invoke(QGEN.format(n=n, chunk=c["text"])).content):
            rows.append({**qa, "source_id": c["id"]})    # source_id = ground-truth relevant doc
    return rows
```

This gives both **retrieval ground truth** (the `source_id` should be retrieved) and
**generation ground truth** (the `answer`). RAGAS has a built-in test-set generator that
does this with question-type diversity (simple, multi-hop, reasoning).

### 11. Generating diverse, realistic questions

Naive generation yields bland, similar questions. Improve diversity by varying:
- **Question type** — factoid, comparison, multi-hop ([T10 §5](10-rag-engineering.md)),
  yes/no, summarization, "not in docs" (should-abstain).
- **Persona/phrasing** — terse vs verbose, expert vs novice, with typos.
- **Difficulty** — single-chunk vs requiring synthesis across chunks.
- **Evolution (Evol-Instruct style)** — take a seed question and prompt the model to make
  it harder, add constraints, or combine concepts.

```python
EVOLVE = """Rewrite this question to require reasoning across MULTIPLE facts (multi-hop),
keeping it answerable from enterprise docs. Original: {q}"""
```

### 12. Generating agent / tool-use trajectories

For agent evals/training, synthesize **(goal, expected tool sequence, expected outcome)**:

```python
TRAJ = """Given these tools: {tool_specs}
Invent a realistic user goal and the ideal ordered tool calls (name + args) to achieve it,
plus the expected final answer. Return JSON."""
```

Use these to score tool-selection and trajectory quality (§3).

### 13. Quality control — synthetic data's biggest risk

Synthetic data can be wrong, repetitive, or unrealistic. **Validate before trusting it:**

- **Filter / verify** — a second LLM (or rules) checks each item is answerable from its
  source and the answer is correct; drop failures.
- **Deduplicate** — embed questions, remove near-duplicates so the set isn't redundant.
- **Human spot-check** — review a sample; calibrate the generator from what's wrong.
- **Ground in real data** — generate from *your* corpus/tools, not the model's imagination,
  so distribution matches production.
- **Watch for model bias / leakage** — don't evaluate a model with data its own family
  generated without a human check; don't train on the eval set.

```python
def verify_item(item) -> bool:
    v = judge.invoke(f"Is this answerable from the source and is the answer correct?\n"
                     f"Source: {item['source_text']}\nQ: {item['question']}\nA: {item['answer']}\n"
                     f"Reply yes/no.").content
    return v.strip().lower().startswith("yes")

clean = [x for x in synthetic if verify_item(x)]      # never skip this step
```

### 14. Uses of validated synthetic data

| Goal | How |
|------|-----|
| Bootstrap RAG eval set | questions-from-chunks (§10) + verify (§13) |
| Improve retriever/reranker | generate (query, positive, hard-negative) triples → fine-tune |
| Train a small classifier (routing, intent) | generate labeled examples, distill from a big model |
| Distillation | strong model generates outputs → fine-tune a cheaper model to match |
| Red-team safety | generate adversarial/injection/PII-bait inputs → test guards (T06/T09) |

### 15. Checklist

- [ ] Eval retrieval and generation separately; add agent trajectory/tool metrics for agents.
- [ ] Adopt a framework (RAGAS/LangSmith/DeepEval); LLM-judge with rubric + reference.
- [ ] Practice judge hygiene: bias mitigation, pairwise where possible, human calibration.
- [ ] Golden set from real traffic + edge + adversarial + out-of-scope; versioned, growing.
- [ ] CI eval gate blocks regressions vs baseline; online logging + drift + failure mining.
- [ ] Generate synthetic eval/training data from your own corpus/tools for ground truth.
- [ ] Maximize diversity (type, persona, difficulty, evolution); dedupe.
- [ ] **Always verify synthetic data** (LLM/rules + human spot-check); never train on the eval set.

---

## Series complete

Part II depth map:

**[10](10-rag-engineering.md)** advanced retrieval → **[11](11-langgraph-features.md)**
LangGraph features · **[12](12-langchain-features.md)** LangChain features →
**[13](13-mcp-tool-calling.md)** MCP & tool-calling · **[14](14-multi-agent-orchestration.md)**
orchestration → **[15](15-prompt-engineering-hallucination.md)** prompts & grounding ·
**[16]** evals & synthetic data.

The LLM-Ops throughline: **measure everything, gate on regressions, ground answers, and
generate (then verify) data to close coverage gaps.** Pair this with Part I's system
blueprint and you have an end-to-end, production-grade practice.
