# 15 — Prompt Engineering & Hallucination Control

> LLM-Ops part 1. Prompts are the program; this is how you write them well, and how you
> stop the model from confidently making things up. Builds on [T06](06-guardrails-evals.md).

---

## Part A — Prompt Engineering

### 1. The anatomy of a strong prompt

A production prompt has clear, separated parts. Order and delimiting matter more than
clever wording.

```
┌─ ROLE / persona ........... "You are a financial-policy assistant."
├─ TASK / instruction ....... what to do, in the imperative
├─ CONTEXT / data ........... retrieved docs, inputs — clearly delimited
├─ CONSTRAINTS / rules ...... must/never, output format, grounding rules
├─ EXAMPLES (few-shot) ...... 1-5 input→output demonstrations (optional)
└─ THE INPUT / question ..... placed LAST (recency aids instruction-following)
```

```python
PROMPT = """You are a financial-policy assistant for internal staff.

Answer the question using ONLY the policy sources provided. Follow these rules:
- Cite each claim inline as [n].
- If the sources don't contain the answer, reply exactly: "I don't have that information."
- Be concise; use a bulleted list when there are multiple conditions.

<sources>
{context}
</sources>

Question: {question}"""
```

### 2. Core techniques (use the simplest that works)

| Technique | What it is | When |
|-----------|-----------|------|
| **Zero-shot** | instruction only | clear, common tasks |
| **Few-shot** | add input→output examples | format/edge-case control |
| **Chain-of-thought (CoT)** | "think step by step" before answering | reasoning, math, logic |
| **Structured output** | force JSON/schema | downstream parsing |
| **Role/persona** | set expertise & tone | consistent voice |
| **Decomposition** | break task into steps/sub-prompts | complex multi-part tasks |
| **Self-consistency** | sample N, take majority | high-stakes reasoning |
| **ReAct** | reason + act with tools | agents (T04/T13) |

> **Reasoning models note:** newer "thinking" models do CoT internally — for them, prefer
> *clear goals and constraints* over explicit "think step by step" scaffolding, which can
> be redundant or counterproductive. Match the technique to the model.

### 3. Structure & formatting that reliably helps

- **Delimit data with tags/markers** (`<sources>…</sources>`, triple backticks). This both
  improves parsing and is a prompt-injection defense — the model learns "this is data, not
  instructions" ([T06 §2](06-guardrails-evals.md)).
- **Put instructions first or last**, not buried in the middle ("lost in the middle").
- **Prefer positive instructions** ("respond in JSON") over negatives where possible, but
  use explicit "never" rules for hard safety constraints.
- **Specify the output format precisely** — show the exact JSON shape or template.
- **Few-shot examples should cover edge cases**, including the "refuse / I don't know"
  case, not just happy paths.

### 4. Few-shot example

```python
FEWSHOT = """Classify the ticket priority. Examples:

Ticket: "Site is completely down for all users." → {"priority": "P1"}
Ticket: "Typo on the about page." → {"priority": "P4"}
Ticket: "Login slow for some users since this morning." → {"priority": "P2"}

Ticket: "{ticket}" →"""
```

### 5. System vs user vs developer roles

- **System / developer prompt:** stable rules, persona, format, safety — set once, cached.
- **User prompt:** the actual request/data — varies per call.
- Keep the **stable prefix** (system + tools + few-shot) constant so provider **prompt
  caching** ([T07 §4](07-fastapi-microservices.md)) cuts cost and latency on every request.

### 6. Parameters that shape output

| Param | Effect | Set to… |
|-------|--------|---------|
| `temperature` | randomness | **0–0.2** for factual/RAG; higher only for creative |
| `top_p` | nucleus sampling | usually leave default; tune one of temp/top_p, not both |
| `max_tokens` | output cap | bound to control cost/runaway |
| `stop` | stop sequences | terminate structured output cleanly |

For RAG and extraction, **low temperature** is a hallucination control in itself.

### 7. Prompt engineering as an engineering discipline

- **Version prompts in git**; treat changes like code (review + eval gate, [T16](16-evals-synthetic-data.md)).
- **Template, don't concatenate** — use a templating layer; never f-string untrusted input
  into instruction positions (injection risk).
- **A/B test against evals**, not vibes — every prompt change runs the eval suite.
- **Keep a prompt registry** so you know exactly which prompt produced which output (audit, [T09](09-security-governance.md)).
- **Iterate empirically:** start simple → measure → add only what the failures demand.

---

## Part B — Hallucination Control

### 8. What hallucination is and why it happens

A **hallucination** is a fluent, confident output **not grounded** in the input or reality.
Causes: the model predicts plausible text, has gaps/staleness in training, gets weak or
missing context, or is pushed to answer when it should abstain. You can't eliminate it,
but layered controls reduce it to acceptable, measurable levels.

### 9. The control stack (layered defense)

```
 1. RETRIEVAL    → give the model the right facts (best ROI)
 2. PROMPTING    → instruct grounding + allow "I don't know"
 3. DECODING     → low temperature, structured output
 4. VERIFICATION → check the answer against sources after generation
 5. ABSTENTION   → refuse / hedge / escalate when unsure
 6. ATTRIBUTION  → cite sources so claims are checkable
```

### 10. Layer 1 — retrieval (highest leverage)

Most RAG hallucinations are *retrieval* failures wearing a generation costume. Fix
retrieval first ([T01](01-rag-pipelines.md)/[T10](10-rag-engineering.md)):
- **Rerank + relevance floor** → if nothing clears the bar, don't force an answer.
- **Enough but focused context** → too little starves the model; too much buries the key
  passage.
- **Component-aware chunks** → coherent, self-contained context.

### 11. Layer 2 — grounding prompts

```python
GROUNDED = """Answer using ONLY the sources. Every factual claim must be supported by a
source and cited as [n]. If the sources are insufficient, reply exactly:
"I don't have enough information to answer that." Do not use prior knowledge.

<sources>{context}</sources>
Question: {q}"""
```

The explicit **abstention escape hatch** ("reply exactly…") is what lets the model *not*
answer — without it, models tend to fabricate rather than admit ignorance.

### 12. Layer 4 — post-generation verification (LLM-as-judge)

For high-stakes answers, a second pass checks that each claim is supported:

```python
FAITHFULNESS = """Sources:
{context}

Answer:
{answer}

List any claim in the Answer NOT fully supported by the Sources.
Return JSON: {{"grounded": bool, "unsupported": [..]}}."""

check = json.loads(judge.invoke(FAITHFULNESS.format(context=ctx, answer=ans)).content)
if not check["grounded"]:
    ans = regenerate_with_warning(ans, check["unsupported"])   # retry, hedge, or flag
```

Related techniques: **citation verification** (every `[n]` maps to a real, on-topic
source), **self-consistency** (sample N answers; disagreement ⇒ low confidence ⇒ hedge),
**chain-of-verification** (model drafts, generates verification questions, answers them,
revises).

### 13. Layer 5 — abstention & calibration

- **Reward "I don't know"** in prompts *and* in your evals (T16) — otherwise you optimize
  for confident wrongness.
- **Confidence signals:** treat low retrieval scores, judge "unsupported" flags, or
  answer disagreement as signals to hedge or escalate to a human ([T04 §7](04-langgraph-agents.md)).
- **Scope guards:** refuse out-of-domain questions instead of guessing.

### 14. Layer 6 — attribution

Inline citations make claims **checkable** by the user and by your automated faithfulness
eval. They also build trust: a cited, source-linked answer is verifiable; an uncited one
is a black box. Render citations as links back to the source document/page (T01 §6).

### 15. What does NOT reliably fix hallucination

- "Just tell it not to hallucinate" — weak on its own; needs the stack above.
- Bigger model alone — helps, but a strong model with bad retrieval still fabricates.
- Higher temperature — makes it worse for factual tasks.
- Fine-tuning for knowledge — teaches style, not facts; use RAG for facts.

### 16. Checklist

- [ ] Strong prompt structure: role, task, delimited context, rules, input last; version it.
- [ ] Match technique to model (few-shot/CoT vs clean goals for reasoning models).
- [ ] Low temperature + structured output for factual tasks; stable cached prefix.
- [ ] Retrieval first: rerank + relevance floor + focused, coherent context.
- [ ] Grounding prompt with an explicit abstention escape hatch + inline citations.
- [ ] Post-generation faithfulness/citation verification on high-stakes answers.
- [ ] Calibrate abstention; escalate on low confidence; refuse out-of-scope.
- [ ] Measure hallucination rate as a tracked metric (T16) — don't rely on vibes.

**Next:** [16 — Eval Frameworks & Synthetic Data](16-evals-synthetic-data.md).
