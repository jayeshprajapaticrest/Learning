# PR Guardian — Org Presentation Pack

A slide-by-slide outline plus a one-page summary. Each slide has a **headline**
(say this), **talking points**, and a **visual** (what to show).

---

## Slide 1 — Title
**Headline:** *PR Guardian — an AI reviewer that's trusted enough to gate merges.*
- Subtitle: Self-improving, human-gated, multi-agent code & release review.
- Visual: the pipeline diagram (intake → reviewers → verify → risk → gate → act → learn).
- Presenter note: emphasize "trusted enough to gate merges" — the whole pitch is *trust*, not novelty.

## Slide 2 — The problem (make it their problem)
**Headline:** *Review is the bottleneck — and inconsistent.*
- Senior engineers spend hours/week on reviews; quality varies by reviewer and time of day.
- The expensive misses are repeat mistakes — the same class of bug that caused a past incident slips through again.
- Security/perf checks depend on whether the reviewer happened to remember the standard.
- Visual: a "time spent on review" + "incidents from preventable PR issues" stat bar (fill with your org's numbers).

## Slide 3 — Why generic "AI code review" hasn't stuck
**Headline:** *The blocker isn't capability — it's trust.*
- Existing tools over-report → engineers mute them (false positives kill adoption).
- Black-box decisions can't gate a merge in a regulated org.
- They don't know *your* standards or *your* past incidents.
- They don't improve from your team's feedback.
- Visual: a "why bots get muted" list with red X's.

## Slide 4 — Our approach
**Headline:** *A team of specialist agents, a skeptic that filters them, and a human who signs off.*
- Multi-agent: security / performance / correctness / style reviewers in parallel.
- Grounded in *our* engineering standards (RAG) and warned by *our* past incidents (similarity search).
- A verifier agent drops weak findings before a human ever sees them.
- Deterministic risk score → decision; human approves anything that affects merge.
- Learns from accept/dismiss feedback.
- Visual: the layered architecture diagram from ARCHITECTURE.md §1.

## Slide 5 — Architecture (the connected components)
**Headline:** *Every AI building block, wired for production.*
- Walk the pipeline diagram left to right; name the technique at each node:
  - intake/act → **MCP** (standard tool interface to GitHub/CI)
  - retrieve → **RAG + vector search** (standards + incidents)
  - reviewers → **multi-agent fan-out**
  - verify → **reflection**
  - risk → **deterministic policy** (LLM explains, code decides)
  - human_gate → **human-in-the-loop** (pause/resume on a checkpointer)
  - learn → **self-improving long-term memory**
- Visual: the README pipeline diagram with each node labeled by technique.

## Slide 6 — Live demo
**Headline:** *Watch it review a real risky PR.*
- Run `python -m prguardian.cli --pr PR-4521`.
- Narrate: it fetches the diff (MCP), grounds in standards (RAG), flags an
  f-string SQL injection + missing authZ, **notices it resembles INC-2024-07**,
  scores it high, and **pauses for your approval** before changing status.
- Then show example 04: dismiss a finding → the reviewer is quieter next run.
- Visual: terminal recording + the generated review report.

## Slide 7 — How we keep it trustworthy
**Headline:** *Five guardrails, by design.*
1. Typed outputs (no free-text parsing).
2. Adversarial verification (low false-positive rate).
3. Deterministic, auditable merge decisions.
4. Human approval gate on every merge-affecting action.
5. Full traceability (LangSmith + run log) for audit.
- Visual: shield icon with the five items.

## Slide 8 — It gets better with use
**Headline:** *Every dismissed finding is a lesson.*
- Accept/dismiss feedback is stored per lens and fed back into prompts.
- Net effect: noise drops, signal stays — adoption compounds instead of decaying.
- Visual: a downward "false positives over time" curve.

## Slide 9 — Measurable, before we trust it
**Headline:** *We ship what we can measure.*
- Evaluation harness scores decision accuracy + recall on labeled PRs.
- Wire into CI: every prompt/model change is regression-tested.
- Metrics to track in pilot (next slide).
- Visual: sample `eval/run_eval.py` output.

## Slide 10 — ROI & success metrics
**Headline:** *What we'll measure in the pilot.*
- **MTTR-style:** time-to-first-review ↓, review cycle time ↓.
- **Quality:** preventable-issue escape rate ↓; % PRs where Guardian caught a real issue.
- **Trust:** finding acceptance rate ↑; mute/ignore rate ↓.
- **Cost:** ~$X per PR in model spend (Sonnet reviewers + one Opus pass) vs. reviewer-hours saved.
- Visual: a before/after metrics table (fill with pilot targets).

## Slide 11 — Rollout plan (de-risked)
**Headline:** *Comment-only → gated → autonomous, earned step by step.*
1. **Shadow / comment-only** (2–4 wks): posts findings, never gates. Measure precision/recall.
2. **Advisory gate** (4 wks): required human approval; Guardian recommends.
3. **Auto-approve the safe tail** (low-risk PRs) with human gate retained on anything that touches merge.
- Each phase has an exit metric. We never skip the human gate on risky changes.
- Visual: a three-phase ramp with gates between phases.

## Slide 12 — Risks & mitigations
**Headline:** *We've thought about the failure modes.*
- Hallucinated findings → verifier + confidence floor + eval gate.
- Prompt injection via PR content → reviewers treat diff as untrusted data; tools are least-privilege via MCP.
- Over-blocking → deterministic thresholds, tunable; human override always available.
- Model/vendor lock-in → LangGraph + MCP keep agents portable; model is one config line.
- Cost blowup → cheap models for fan-out; one expensive pass; budget caps.
- Visual: risk → mitigation two-column table.

## Slide 13 — Roadmap
**Headline:** *Where this goes.*
- More lenses (accessibility, i18n, licensing/compliance).
- Auto-generated release notes & changelogs from verified findings (already drafted by the report node).
- Cross-PR knowledge graph of recurring issues.
- Same engine, new surfaces: incident triage, infra-change review.
- Visual: roadmap timeline.

## Slide 14 — The ask
**Headline:** *Greenlight a 6-week shadow-mode pilot on one repo.*
- Need: one pilot repo, read access via a GitHub MCP token, a metrics baseline, and a named eng sponsor.
- Deliverable: precision/recall + reviewer-time data to decide on the advisory-gate phase.
- Visual: a single clear "Phase 1 pilot" box with the asks listed.

---

## One-pager (leave-behind)

**PR Guardian** is a multi-agent system that reviews pull requests with the
judgment and guardrails an enterprise needs to actually act on its output.

**What it does:** A team of specialist AI agents (security, performance,
correctness, style) reviews each PR in parallel, grounded in *our* engineering
standards and warned when a change resembles *our* past incidents. A separate
verifier agent filters out weak findings. A deterministic policy scores risk and
proposes a decision. **A human approves anything that affects a merge.** It then
acts on GitHub/CI and **learns from which findings the team accepts**, getting
quieter and sharper over time.

**Why it's different:** It's engineered for *trust*, not novelty — typed
outputs, adversarial verification, deterministic auditable decisions,
human-in-the-loop gates, full traceability, and a built-in evaluation harness.

**Built on:** LangGraph (orchestration), Claude (Opus 4.8 for judgment, Sonnet
4.6 for the parallel fan-out), RAG over a vector store, and the Model Context
Protocol for portable GitHub/CI integration. Production hardening is a config
change, not a rewrite.

**The ask:** a 6-week shadow-mode pilot on one repo to produce the
precision/recall and reviewer-time data that justify turning the gate on.

**Tech topics demonstrated (for the curious engineer):** single + multi-agent
orchestration, RAG, vector storing/searching, MCP tools, short/long-term memory,
reflection/verification, human-in-the-loop, deterministic decisioning,
self-improving feedback, observability, and evaluation.
