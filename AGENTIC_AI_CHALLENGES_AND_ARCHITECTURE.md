# Agentic AI — Component Challenges, Failure Modes & Architectural Decisions

> Companion to `AGENTIC_AI_COMPLETE_GUIDE.md`. That document covers **how to build** each component; this one covers **what goes wrong with each component, why it goes wrong, and the competing approaches for handling it** — at both the component level and the system-architecture level.
>
> Format used throughout: **Challenge → root cause → candidate approaches with trade-offs → decision guidance.** Mechanics already explained in the first document (the loop contract, caching rules, RAG pipeline stages, MCP wiring) are referenced, not repeated.

---

## Table of Contents

1. [A Taxonomy of Agent Failures](#1-a-taxonomy-of-agent-failures)
2. [Context Window Failures & Management Approaches](#2-context-window-failures)
3. [Memory Architecture — The Approach Space in Depth](#3-memory-architecture)
4. [Reasoning & Planning Failures](#4-reasoning--planning-failures)
5. [Tool-Layer Failures](#5-tool-layer-failures)
6. [RAG — Operational & Lifecycle Challenges](#6-rag--operational-challenges)
7. [MCP & Integration-Layer Challenges](#7-mcp--integration-challenges)
8. [Multi-Agent Coordination Failures](#8-multi-agent-coordination-failures)
9. [State, Durability & Long-Running Execution](#9-state-durability--long-running-execution)
10. [Identity, Authorization & Agent-to-Agent Interop](#10-identity-authorization--interop)
11. [Drift, Versioning & Change Management](#11-drift-versioning--change-management)
12. [Debugging & Non-Reproducibility](#12-debugging--non-reproducibility)
13. [Human–Agent Interaction Design Challenges](#13-humanagent-interaction)
14. [Architectural Decision Records — The Big Trade-offs](#14-architectural-decision-records)

---

## 1. A Taxonomy of Agent Failures

Before component-level detail, the map. Production agent failures cluster into five families, and **the family determines where you fix it** — most wasted engineering effort comes from fixing the wrong layer (e.g., prompt-tuning a problem caused by context pollution, or adding tools when the planner is the problem).

| Family | Symptom signature | Fix layer |
|---|---|---|
| **Specification failures** | Agent does the wrong task confidently; output format wrong; ignores constraints | Task brief, system prompt, output contract |
| **Context failures** | Agent was right early, degrades over the session; forgets the goal; repeats work | Context management (§2), memory (§3) |
| **Capability failures** | Model genuinely can't do the step (math, niche domain, perception) | Model choice, tool substitution (give it a calculator/SQL, don't prompt harder) |
| **Coordination failures** | Each agent locally fine, system-level outcome wrong; lost information between agents; duplicated/conflicting work | Orchestration contracts (§8) |
| **Environment failures** | Tool flakiness, rate limits, stale data, permissions — the world misbehaved | Harness engineering: retries, idempotency, durability (§9) |

Two cross-cutting facts shape everything below:

- **Errors compound multiplicatively across steps.** A step-level reliability of 95% gives ~36% success over 20 dependent steps (0.95²⁰). Long-horizon agents are therefore engineered around *error recovery and verification*, not around making each step perfect — you cannot prompt your way to 99.9% per-step accuracy, but you can build loops that detect and repair.
- **Failures are usually silent.** Unlike conventional software, the agent doesn't throw — it produces plausible wrong output. Every architectural pattern in this document exists to convert silent failures into detectable ones.

---

## 2. Context Window Failures

The first document covered context-management *mechanisms* (editing, compaction, sub-agent offloading). This section covers the **failure physics** those mechanisms exist to fight, and the decision space between them.

### 2.1 Context rot: long context ≠ usable context

Models advertise 200K–1M token windows, but **effective** attention degrades well before the limit. Empirically observed (needle-in-haystack and long-horizon evaluations across vendors):

- **Positional bias ("lost in the middle")** — information at the start and end of context is recalled far better than the middle. Architectural consequence: put the task statement and output contract near the *end* of the assembled prompt (or re-state them), never only at position 0 of a 150K-token transcript.
- **Degradation is content-dependent** — distractor-heavy context (many near-relevant chunks, repeated similar tool outputs) degrades recall faster than clean context of the same length.
- **Reasoning degrades before recall** — a model can still *find* a fact at 200K tokens but combine facts across the window noticeably worse. Long-context retrieval benchmarks overestimate long-context *agency*.

**Design rule that follows:** treat the context window as having a **soft working budget far below the hard limit** (a common operating point: keep the active transcript under ~40–60% of the window before compaction triggers) and optimize for *context quality density*, not capacity utilization. "It fits" is not the bar; "every token earns its place" is.

### 2.2 The four context pathologies

A useful working taxonomy (popularized in the agent-engineering community, consistent with vendor guidance) — diagnose which one you have before choosing a fix:

| Pathology | What happens | Typical trigger | Primary fix |
|---|---|---|---|
| **Context poisoning** | A hallucination or wrong tool result enters context and gets *re-referenced as fact* by later steps | Agent summarizes its own error into a "finding"; bad OCR; stale cache | Validation at entry (check tool outputs before they persist); quarantine: keep raw observations separate from conclusions; targeted deletion of the poisoned span |
| **Context distraction** | Past a size threshold the model over-attends to the accumulated history and under-attends to its trained reasoning — it starts *imitating its own transcript* (repeating past actions) instead of planning | Very long single sessions | Compaction with re-stated goal; fresh-context sub-agent for the next phase |
| **Context confusion** | Irrelevant-but-present content (unused tool schemas, off-topic retrievals) influences output — the model uses things *because they're there* | Tool overload; un-reranked RAG dumps | Reduce surface: tool search/deferred schemas, rerank-then-prune retrieval, remove dead instructions |
| **Context clash** | Contradictory information coexists (old plan vs. new plan, doc v1 vs. v2, user correction vs. earlier assumption) and the model interleaves both | Multi-turn accumulation without supersession | Explicit supersession: when information is updated, *replace* don't append; "current state" blocks that override history; versioned facts in memory |

**The architectural insight common to all four:** appending is the default but *appending is not neutral* — every retained token is a standing influence on future behavior. Mature agents have an explicit **context-write policy** (what gets in), **retention policy** (what stays), and **supersession policy** (what overrides what), not just a transcript.

### 2.3 Choosing between the mechanisms

| Approach | Information loss | Cost profile | Reversible? | Failure mode it introduces |
|---|---|---|---|---|
| **Truncation (sliding window)** | High — oldest turns gone entirely | Free | No | Goal/constraint loss when the task statement scrolls off |
| **Context editing (prune stale tool results)** | Low if pruned items truly stale | Free (saves tokens) | No | Pruning a result a later step needed; mitigate: keep the *fact*, drop the *payload* |
| **Compaction (summarize old history)** | Medium — lossy by design | One LLM call per compaction | No | **Summary bias**: the summarizer's interpretation replaces ground truth; errors in the summary are now poisoned context with no raw data to check against |
| **Offload to environment (write notes/files, re-read on demand)** | None — full data preserved outside context | Cheap writes; reads on demand | Yes | Agent forgets to consult its notes; mitigate: index-in-context, instructions to check |
| **Fresh-context sub-agent per phase** | Controlled — only the brief and report cross the boundary | Extra orchestration tokens | Yes (parent intact) | Under-specified briefs (see §8.2) |

**Decision guidance:** these compose; the question is ordering. A robust default stack for long-running agents: (1) aggressively prune bulky tool payloads after use, keeping one-line conclusions; (2) offload durable findings to files/notes continuously (so compaction has a safety net); (3) compact when crossing the soft budget, with the compaction prompt explicitly instructed to preserve: the original task, all user corrections/decisions, current plan state, and open questions; (4) phase-boundary resets via sub-agents for multi-phase work. Systems that rely on compaction *alone* hit summary-bias failures; systems that pair compaction with environment-offload can always re-derive lost detail.

### 2.4 An underrated failure: instruction decay

System-prompt rules measurably lose force as the transcript grows — an instruction at token 500 competes with 100K tokens of subsequent context. Handling approaches:

- **Re-injection**: periodically restate critical constraints near the end of context (system-role mid-conversation messages where supported, or harness-injected reminder blocks). This is what production harnesses (including coding agents) actually do.
- **Structural enforcement** beats verbal enforcement: a rule like "never call X without approval" should be a permission gate in the harness, not (only) a sentence in the prompt. Prompts decay; code doesn't.
- **Checklists as state**: convert multi-constraint tasks into an explicit todo/checklist artifact the agent updates — constraints become visible state instead of memory.

---

## 3. Memory Architecture

The first document established the memory *hierarchy* and file-based memory rules. This section treats the **full approach space** for persistent agent memory — the worked example of "one challenge, many architectures" — because memory is where the most divergent legitimate designs exist.

### 3.1 The four design problems every memory system must answer

1. **The write problem** — *what* is worth remembering, *when* is it extracted, and *who decides*? (Remember too much → noise that misleads retrieval; too little → groundhog-day agents.)
2. **The read problem** — how does the right memory reach the context at the right time without flooding it?
3. **The update/forget problem** — facts change ("user moved teams"); memories contradict; stale memory is *worse than no memory* because it's trusted.
4. **The provenance problem** — when a memory drives an action, can you trace where the memory came from? (Required for debugging poisoned memory and for compliance deletion.)

Every architecture below is a different point in this 4-dimensional space.

### 3.2 The approach space, compared

**A. Append-only log + in-context recap.** Store full transcripts; at session start, an LLM pass produces a recap injected into context.
- *Write*: trivial (everything). *Read*: recap quality bounds everything. *Forget*: never. *Provenance*: perfect.
- Fails at scale: recap of 200 sessions is either huge or vague. Fine for low-session-count assistants; a dead end beyond that.

**B. Structured file/notes memory (agent-curated).** The agent itself maintains a directory of small fact-files plus an index loaded each session; it has read/write/edit tools over them.
- *Write*: model judgment at experience time (highest-fidelity moment to decide salience). *Read*: index in context, full notes on demand — progressive disclosure. *Update*: natural — the agent edits the file. *Provenance*: good if files cite their source session.
- **Failure modes**: write-skipping (model doesn't bother) → fix with explicit prompt policy + end-of-session "what did you learn" step; duplicate sprawl → fix with "update-don't-create" instruction + periodic consolidation pass; index bloat → cap index size, archive.
- The dominant pattern in practice for single-tenant/developer agents (this is how Claude Code, and the standardized memory tool, work). Its honest limitation: retrieval is by *name/index scan*, so it degrades when memory grows beyond what an index skim covers.

**C. Vector-store memory (retrieval-based).** Each memory is embedded; relevant memories retrieved by similarity to the current task and injected automatically.
- *Write*: usually an extraction pipeline (an LLM pass over each session distills candidate memories). *Read*: automatic, scales to millions of entries. *Update*: **the weak axis** — similarity search returns both the stale and fresh version of a fact and the model must reconcile (context clash, §2.2); deduplication needs a separate reconciliation step (compare new memory against nearest neighbors → decide add/update/merge/skip — this is how dedicated memory layers like Mem0-class systems work).
- *Provenance*: must be engineered (store source pointers as metadata).
- **Failure modes**: irrelevant-memory injection (retrieval fires on surface similarity — a memory about "Python the snake" surfaces for Python code); memory poisoning at scale (one bad extraction permanently pollutes retrieval — see §3.4); silent contradiction accumulation.

**D. Knowledge-graph / temporal memory.** Memories stored as entities + relations with **validity intervals** (fact X held from t1 to t2, superseded by Y). Retrieval = graph queries + embedding search over nodes (Zep/Graphiti-class systems).
- Directly solves the update/forget problem (supersession is first-class: facts are *invalidated*, not deleted) and multi-hop questions ("what changed about the client's stack since March?").
- Cost: an extraction pipeline (entity/relation extraction per session — LLM calls), schema/ontology maintenance, and a real database. The highest-engineering-cost option; justified when memory queries are relational/temporal, not just "recall relevant facts".

**E. Hierarchical paged memory (MemGPT/Letta-style).** Treat context as main memory and external store as disk, with the **agent itself issuing page-in/page-out calls** via memory tools — an OS metaphor. Core memory (always in context: persona, key user facts, editable by the agent) + archival/recall memory (searched on demand).
- Strength: the agent *self-manages* its in-context working set, including editing its always-loaded core block when fundamentals change (clean supersession for the most important facts).
- Weakness: relies on the model's judgment about *when* to page; failure mode is the model not searching archival memory when it should — same trigger-reliability issue as B, mitigated with prompt policy.

**F. Fine-tuning / model-weight memory.** Periodically train on accumulated experience.
- Not interactive memory at all (days latency, no per-user separation, no deletion guarantee — a GDPR problem). Appropriate only for distilling *population-level* lessons (org style, domain vocabulary) into a base model. Never the answer to "remember what this user said."

### 3.3 Decision guidance

| Situation | Recommended architecture |
|---|---|
| Developer/single-tenant agent, ≤ thousands of facts | **B** (file memory) — debuggable (a human can read it), zero infra, natural updates |
| Consumer product, millions of users, "remembers me" features | **C** with a reconciliation pipeline (add/update/merge/skip against nearest neighbors), per-user partitions, provenance metadata |
| Memory queries are relational/temporal (CRM-like, account history) | **D** (temporal knowledge graph) |
| Long-lived autonomous agent that must self-manage what's "front of mind" | **E** (core + archival), often with B-style files as the archival tier |
| All of the above | Hybrid is normal: core block (E) + files (B) for procedures + vector tier (C) for scale. The mistake is *not choosing* write/update/forget policies, not choosing the "wrong" store. |

### 3.4 Memory-specific risks that don't exist elsewhere

- **Memory poisoning is worse than context poisoning** — a poisoned context dies with the session; a poisoned *memory* re-injects into every future session, and (if memory came from untrusted content) is a **persistence mechanism for prompt injection**: an attacker's instruction stored as a "preference" replays forever. Mitigations: never write memories directly from untrusted content without a validation pass; tag memories by source trust level; make memory human-inspectable; support targeted deletion.
- **Self-reinforcement loops**: agent writes a wrong conclusion → recalls it next session as established fact → acts on it → writes confirmation. Break the loop with provenance ("this memory came from *my own inference*, not user statement — verify before relying on it") — distinguishing **observed** facts from **inferred** ones in the memory schema is cheap and high-value.
- **Cross-tenant leakage**: one shared vector index with a metadata filter is one missing `WHERE` clause away from leaking user A's memories to user B. Physical per-tenant partitioning (separate collections/namespaces) over logical filtering wherever the data is sensitive.
- **The forgetting requirement is legal, not just hygienic**: deletion requests must propagate to extracted memories, embeddings, *and summaries derived from them* — design the lineage tracking before you need it.

---

## 4. Reasoning & Planning Failures

### 4.1 The failure inventory

| Failure | Signature | Root cause |
|---|---|---|
| **Goal drift** | Agent solves a related-but-different problem; quality of *steps* stays high | Original objective diluted/scrolled out; sub-task success substituted for task success |
| **Looping / thrashing** | Repeats the same failing action with trivial variations | No progress signal in context; the failed attempt looks like the most relevant precedent (context distraction) |
| **Premature completion** | Declares success with work unverified or partial | "Done" is not operationalized; model optimizes for *plausible completion narrative* |
| **Over-planning / analysis paralysis** | Long deliberation, option-enumeration, no action | Effort/reasoning miscalibrated to the task; ambiguity it won't resolve by acting |
| **Over-engineering** | Unrequested refactors, abstractions, defensive code | Model's helpfulness prior exceeds the task scope |
| **Fabricated progress** | Status reports claim steps that never ran | Narration generated from plan rather than from observations |
| **Sunk-cost rigidity** | Keeps extending a failed approach instead of backtracking | Its own transcript is its strongest precedent; no explicit backtrack affordance |

### 4.2 Handling approaches

**Operationalize "done" — the single highest-leverage fix.** Vague goals produce premature completion; checkable goals produce verification. Approaches, weakest → strongest:
1. Prose definition-of-done in the prompt.
2. **Explicit acceptance checklist as an artifact** the agent must check off with evidence per item.
3. **Programmatic verification the agent must run** (tests, schema validators, linters) — "done means this command exits 0."
4. **Independent verifier** — a fresh-context agent grades the work against the spec (self-review in-context is systematically lenient; the generator's context contains its own rationalizations).
5. **Rubric-graded outcome loops** — the harness itself iterates generate→grade→revise until a rubric passes or budget exhausts (this is productized in hosted runtimes as "outcomes"; the rubric must be *independently gradeable criteria*, not vibes — same discipline as LLM-judge rubrics).

**Anti-looping.** (a) Harness-level detection: hash recent tool calls; on a repeat-with-trivial-variation, inject an intervention message ("you have tried X twice with the same failure; state why it failed and propose a different approach"); (b) make failure *legible* — error results that explain (`is_error` + cause) loop far less than opaque failures; (c) budget-per-approach: prompt the agent to set an attempt budget and explicitly backtrack ("if two repair attempts fail, revert and rethink the approach").

**Anti-drift.** Keep the task statement + constraints in a *pinned* position (re-injected near the context tail, §2.4); for long runs, require a periodic "objective check" step (one sentence: what was asked, what I'm doing, are these the same?). In plan-then-execute designs, store the plan as an editable artifact — drift becomes a visible diff against the plan instead of an invisible slide.

**Fabricated progress.** Require claims to be grounded in tool results: "before reporting progress, point to the tool output that proves each claim; unverified items must be labeled unverified." This near-eliminates fabricated status in long autonomous runs and is cheap. Architecturally: derive user-facing status from *harness telemetry* (which tools actually ran) where possible, not from the model's narration.

**Calibrating deliberation.** Reasoning depth is now a per-request control (adaptive thinking + effort), so over/under-thinking is a *configuration* problem before it's a prompt problem: route routine steps at low effort, escalate on failure. The newest frontier models invert an old assumption — higher up-front reasoning often *reduces* total cost on agentic work (fewer wasted actions), so measure end-to-end cost, not per-request cost, when tuning.

### 4.3 Plan-first vs. react-as-you-go (architectural choice)

| | Plan-then-execute | Incremental (ReAct-style) |
|---|---|---|
| Strength | Inspectable/approvable plan; parallelizable steps; drift is diffable | Adapts to what it discovers; no stale-plan problem |
| Weakness | Plans go stale on contact with reality; replanning machinery needed | Myopia; local decisions can paint into corners |
| Use when | Cost of wrong action high (approval gates on the *plan*), task decomposable up front | Exploration-heavy tasks where step N+1 depends on observing step N |

Mature systems blend: **plan as a living artifact** — produced up front, executed incrementally, *edited* (not abandoned) when reality disagrees, with replans logged. The plan artifact doubles as the checkpoint for resumability (§9).

---

## 5. Tool-Layer Failures

Beyond the design rules in the first document, these are the tool problems that surface *in operation*:

### 5.1 Wrong-tool and missed-tool selection

- **Overlapping tools** are the top cause: `search_kb`, `search_docs`, `lookup_articles` with mutually intelligible descriptions force a coin-flip. Fix structurally: merge tools, or make one a parameter of the other (`search(corpus=...)`). Selection accuracy is mostly a *menu design* problem.
- **Under-triggering** (model answers from memory instead of calling the tool) has shifted to the dominant failure on newer models, which are more conservative about tool use. Fix in the tool **description** ("call this whenever X; do not answer X from prior knowledge") — trigger conditions in descriptions measurably outperform system-prompt exhortations.
- **Capability illusion**: if a tool exists in the menu, the model assumes it works for adjacent purposes. Document *non*-capabilities ("returns metadata only, not file contents") to prevent confident misuse.
- Maintain a **labeled tool-selection eval** (prompt → expected tool(s)); selection regressions from prompt or model changes are otherwise invisible until production.

### 5.2 Argument-level failures

Schema-valid but semantically wrong arguments: plausible-but-fabricated IDs, relative dates resolved against the wrong "today", units, off-by-one pagination. Handling layers: (a) **don't make the model copy opaque identifiers** it has only seen once — design tools to accept the natural key the user gave ("order for jane@x.com on May 3") and resolve internally, or have prior tool results return *short stable handles* the model references; (b) inject "today's date" explicitly (models don't know it); (c) validate semantics in the handler and return corrective errors ("customer_id not found; did you mean one of: ...") — a corrective error converts a failure into a one-step recovery.

### 5.3 The tool-result ingestion problem

Tool outputs are the *largest uncontrolled input* to your context. Three operational rules: **truncate with signposting** (state "showing 50 of 4,210 rows; refine the query" — silent truncation makes the model believe it saw everything, a poisoning vector); **normalize errors** across tools into one shape (`{error, cause, suggested_next_step}`) so recovery behavior generalizes; **mark provenance** — results from tools that touch untrusted content (web, email, third-party MCP) should be visibly tagged as untrusted data in context, because the next failure class is injection via tool results, and downstream steps need to know what *kind* of evidence they're standing on.

### 5.4 Side-effect semantics (the hardest tool problem)

The model may emit the same call twice (after an ambiguous result, after a retry, after resume-from-checkpoint). For side-effectful tools this is a correctness crisis, handled the way distributed systems handle it:

- **Idempotency keys**: harness attaches a deterministic key (hash of tool_use id) to mutating calls; the backend deduplicates. The single most important pattern for "agent charged the card twice".
- **Two-phase tools**: split `prepare_refund` (returns a quote + confirmation token) from `execute_refund(token)` — the model gets a natural review point, the harness gets a gate, retries of phase 1 are free.
- **Compensation over prevention** where the backend supports it (create → delete is cheap; some actions can only be compensated, not prevented).
- Classify every tool in a registry: `read_only | idempotent_write | non_idempotent_write | irreversible` — this classification drives retry policy, parallelism (only `read_only` runs concurrently by default), approval gating, and checkpoint semantics (§9). If you don't have this table, you have implicit `irreversible` everywhere or implicit `read_only` everywhere; both are wrong.

---

## 6. RAG — Operational Challenges

The first document covered the pipeline. These are the problems that appear after it ships:

### 6.1 Index freshness and the sync problem

The index is a **derived materialized view** of source systems, and it drifts. Decide explicitly:

| Strategy | Staleness | Cost/complexity | Use when |
|---|---|---|---|
| Periodic full re-index | Hours–days | Simple, expensive at scale | Small corpora, weekly-changing docs |
| Incremental on change events (webhooks/CDC) | Minutes | Pipeline + dead-letter handling; partial-failure states | Most production systems |
| Query-time hybrid (index for bulk + live API tool for hot entities) | None for hot data | Two retrieval paths to maintain | Order status, prices, anything where stale = wrong |

Unhandled corollaries that bite: **deletion propagation** (revoked/deleted source docs must leave the index *and* any caches/summaries — also a compliance requirement); **chunk orphaning** (doc updated → old chunks must be replaced atomically or queries see v1 and v2 simultaneously = context clash); **permission drift** (ACLs change after indexing — enforce permissions at *query* time against the source of truth, or re-sync ACL metadata aggressively; stale-ACL leakage is a reportable incident, not a quality bug).

### 6.2 Embedding model migration

Changing embedding models means **re-embedding the entire corpus** (vectors from different models aren't comparable). Architect for it from day one: store raw chunk text + metadata independently of vectors (re-embedding = re-running one stage, not re-ingesting); version the index (`collection_v2`) and cut over blue/green with a retrieval-eval gate; never mix model versions in one searched collection. Teams that skipped this run years-old embedding models because migration was never made cheap.

### 6.3 Quality drift without code changes

Retrieval quality degrades as the *corpus* changes — new near-duplicate documents split votes between copies; growing corpus dilutes top-k; new jargon isn't represented. Treat the §5.7 (doc 1) eval set as a **continuously running monitor** (run nightly against the live index, alert on Recall@k regression), not a one-time tuning artifact. Add corpus hygiene: near-duplicate detection at ingestion, canonical-document policies.

### 6.4 Agentic-RAG-specific issues

When retrieval is a tool the agent calls: **query laziness** (one broad query, accepts mediocre results — fix in tool description: "if results don't directly answer, reformulate and search again; try at most 3 formulations"); **retrieval loops** (re-searching minor variants — cap via harness); **citation laundering** (agent summarizes retrieved text into its notes, then later cites its *note* as the source — provenance must travel with the fact through memory writes).

---

## 7. MCP & Integration Challenges

Operational issues beyond the wiring covered in doc 1:

- **Server sprawl and the N×schema tax.** Each connected server adds always-loaded schemas (context confusion, §2.2) and an availability dependency. Govern like dependencies: an allowlist registry with owners, pinned versions, and per-agent server budgets; prefer *tool-level* allowlisting over importing entire servers (a 40-tool server for one needed tool is 39 distractors plus attack surface).
- **Version/contract drift.** MCP servers update independently of your agent; a tool's schema or semantics can change under you with no compile-time signal. Handle as you would a flaky upstream API: contract tests in CI against pinned server versions (call each allowlisted tool with canned inputs, assert response shape), and treat unexpected schema diffs as deploy blockers.
- **Auth lifecycle.** Remote servers run OAuth; tokens expire mid-session. Decide the UX for re-auth interrupts up front (queue the action and resume after refresh vs. fail the step). Centralize credentials (vault/broker keyed by server URL with auto-refresh) instead of per-agent token storage — token sprawl across agent configs is both an ops and a security failure.
- **Trust is per-server, not per-protocol.** MCP standardizes the *pipe*, not the trustworthiness of what flows through it. Tool descriptions themselves are injectable content ("tool poisoning") and can be *changed by the server after you reviewed them* (rug-pull) — pin and hash server definitions where the deployment matters; review diffs on update like a dependency bump.
- **The composition gap.** MCP gives you tools; it doesn't give you *cross-server transactions*. "Create the Jira ticket, then link it in Slack" can fail halfway with no rollback — the compensation logic (§5.4) is yours, and it's easy to forget that a multi-server sequence is a distributed transaction with no coordinator.

---

## 8. Multi-Agent Coordination Failures

Doc 1 gave the topologies. This section is the failure analysis — multi-agent failures are **system-level**: each agent's transcript looks fine in isolation.

### 8.1 Where multi-agent systems actually fail

Empirical studies of failed multi-agent runs (academic taxonomies like MAST and practitioner postmortems agree) cluster the causes as roughly: **specification/decomposition problems** (ambiguous or overlapping sub-task briefs), **inter-agent misalignment** (information lost or distorted at boundaries, agents assuming others know things they don't), and **verification gaps** (no one checks integrated output; sub-results accepted on assertion). Model capability is rarely the binding constraint — **the contracts between agents are.**

### 8.2 The context-transfer problem (the central one)

Sub-agents share no history. Every boundary crossing is a lossy serialization, in both directions:

- **Downward loss (briefing)**: the orchestrator omits a constraint it "knows" → the worker solves a subtly different problem *competently* — the most expensive failure because it looks like success. Handle with a **brief template** enforced in the spawn-tool schema (objective / constraints / context that would surprise you / output contract / budget) — required fields convert forgetting into a visible validation error. A stronger variant: workers must restate the task in their first response; the orchestrator (or a cheap check) compares restatement to intent before the worker burns budget.
- **Upward loss (reporting)**: the worker found 12 things, reported 5 "relevant" ones; relevance was orchestrator-context-dependent. Handle with structured report contracts that separate `findings` / `evidence` / `anomalies_noticed` / `open_questions` / `confidence` — the anomalies field exists precisely to carry "I don't know if you care about this."
- **Telephone-game compression**: in pipelines (A→B→C), each hop re-summarizes; by C, nuance is gone. Handle by passing **artifacts, not paraphrases**: workers write full output to the shared environment (files); the message channel carries pointers + deltas. The environment becomes the high-bandwidth channel; messages stay control-plane.

### 8.3 Concurrency and conflict

Parallel workers in a shared workspace recreate classic distributed-systems races with worse actors (agents don't honor implicit locks):

| Approach | Mechanism | Trade-off |
|---|---|---|
| **Partition (preferred)** | Decompose so workers own disjoint resources (files, modules, accounts) | Pushes the problem into decomposition quality — which you must do well anyway |
| **Workspace isolation + merge** | Each worker in its own copy (git worktree/branch); orchestrator merges | Merge conflicts surface *as conflicts* (visible) instead of clobbers (silent); merge step needs real logic |
| **Pessimistic locks** | Harness-held leases on resources | Agents wait; deadlock handling; usually overkill |
| **Optimistic + verify** | Let conflicts happen; integration verification catches them | Only viable with strong programmatic verification (tests) downstream |

Also: **duplicated work** (two workers independently solve the same sub-problem — orchestrator must own a visible task ledger with assignments) and **divergent assumptions** (workers make incompatible local decisions, e.g. two naming conventions — put shared conventions in every brief, or designate one worker's output as the standard others must conform to).

### 8.4 Error propagation and the verification layer

A worker's confident-but-wrong report becomes the orchestrator's poisoned context (§2.2) — multi-agent systems *launder* uncertainty into apparent fact at each boundary. The architecture answer is a **verification layer at integration points**, scaled by stakes: schema/programmatic checks on every report (free) → spot-check sub-results against raw artifacts (cheap) → independent verifier agent on the integrated result (the fresh-context principle again) → adversarial verification for high-stakes findings (a skeptic agent instructed to *refute* each claim; claims surviving N independent refutation attempts are promoted). Budget verification as a first-class cost — mature systems spend a meaningful fraction (commonly ~10–30%) of total tokens on checking, and it is usually the best-spent fraction.

### 8.5 Cost/latency containment

Multi-agent cost failure is structural, not incidental: every worker re-pays context establishment, and orchestrators left unconstrained over-spawn. Containment: per-worker budgets in the brief (enforced by the harness, reported in the ledger); orchestrator prompt guidance keyed to task size (doc 1 §7.4); **fan-out caps** per turn; model tiering at the worker boundary; and a kill-switch metric — tokens-per-completed-subtask — monitored per run so a flailing fleet is stopped, not discovered on the invoice.

---

## 9. State, Durability & Long-Running Execution

Agents that run for minutes–hours–days hit failures that prompt engineering cannot touch: processes crash, rate limits hit, deploys happen mid-run.

### 9.1 The resumability problem

An agent's effective state = (message history) + (environment changes already made) + (in-flight intent). A naive restart loses the third and *re-executes against* the second — re-running side effects (§5.4).

| Approach | What it gives you | Cost |
|---|---|---|
| **Transcript persistence + replay** | Resume = reload messages, continue the loop. Works because the transcript *is* the state | Must persist atomically per turn; side effects since last persist may re-fire → needs idempotency keys |
| **Checkpoint at step boundaries** (LangGraph-style: persist graph state after each node) | Resume from last completed step; time-travel debugging (rewind to step N, fork) | You adopt a state-graph structure; checkpoint store becomes critical infra |
| **Durable-execution engines** (Temporal/Restate-class: every step recorded; on crash, completed steps replay from the log without re-executing) | Exactly-once *effects* with at-least-once execution; survives deploys; the gold standard for side-effect-heavy agents | Code must be structured as deterministic workflow + non-deterministic activities; LLM calls and tool calls become recorded activities; real platform adoption |
| **Event sourcing** (append-only event log of everything; state = fold(log)) | Perfect audit + provenance; natural fit since agent sessions *are* event streams (hosted agent runtimes expose exactly this shape) | You build the projections; log compaction eventually needed |

**Decision guidance**: short interactive sessions → transcript persistence + idempotent tools is enough. Anything autonomous and side-effectful that runs > a few minutes → checkpointing at tool boundaries with idempotency keys is the floor; durable-execution semantics (home-grown or platform) for financial/irreversible domains. The unifying invariant: **persist intent before executing effects** (write "about to call refund(X), key=K" durably, then call) — this single discipline makes crash-recovery decidable.

### 9.2 Interruption, steering, and cancellation

Long-running agents need a control plane, not just a start button: **graceful interrupt** (stop at the next safe boundary — never mid-write; an interrupt mid-transaction is itself a consistency bug), **steering** (queued user messages that the agent incorporates without restarting — event-queue semantics), and **cancellation with cleanup** (compensate or quarantine partial work; "cancelled" must leave the environment in a *labeled* state, not an unknown one). If you build on an event-stream architecture (§9.1), these fall out naturally as event types; if you build request/response, you will retrofit them painfully.

### 9.3 Rate limits and fleet-level backpressure

Single-agent retry logic does not survive multi-agent fan-out: 20 workers hitting one org-level token budget create synchronized retry storms. Fleet-level handling: a shared **token-budget governor** (central concurrency/TPM accounting, workers acquire before calling), jittered backoff, priority classes (interactive sessions preempt batch agents), and degradation policy (under sustained pressure: shed lowest-priority runs and shrink fan-outs rather than slowing everything uniformly). Offload all non-interactive work to batch endpoints — half price *and* off the interactive rate pool.

---

## 10. Identity, Authorization & Interop

### 10.1 The agent identity problem

"Who is acting?" has three legitimately different answers, and conflating them is the root of most agent-authz incidents:

1. **The user** the agent acts for, 2. **the agent workload** itself, 3. **the developer/org** that operates it.

The classic failure is the **confused deputy**: the agent holds a powerful service credential (answer 3) and is steered — by a user or by injected content — into using it for something the *user* (answer 1) was never entitled to do. The agent becomes a privilege-escalation proxy.

**Handling approaches, weakest → strongest:**
- One shared service account for the agent (status quo in too many deployments): no per-user attribution, maximal confused-deputy surface. Acceptable only for read-only, non-sensitive tools.
- **On-behalf-of (delegated) credentials**: the agent's calls to downstream systems carry the *end user's* delegated, scoped token (OAuth token-exchange patterns) — downstream authz then enforces the user's actual entitlements, and the deputy can't be confused into exceeding them. This is the direction the ecosystem is standardizing on; treat it as the default for any tool touching user-owned data.
- **Task-scoped, short-lived credentials**: minted per run, scoped to the resources the *plan* needs, expiring with the run — limits the blast radius of both injection and bugs to one task's scope.
- Plus invariants regardless of scheme: agent actions **attributable** in audit logs as `(user, agent, session, tool_use_id)` — "the agent did it" must never be the end of an audit trail; **authz enforced in the tool handler/downstream**, never by prompt ("you may only access your own records" in a system prompt is a wish, not a control).

### 10.2 Agent-to-agent interop (beyond one runtime)

Inside one system, your orchestrator owns coordination (§8). Across organizational/vendor boundaries, interop protocols are emerging — notably **A2A (Agent2Agent)**: agents publish capability "agent cards", exchange *tasks* with lifecycle states over HTTP/SSE, and remain **opaque** to each other (no shared context/tools — by design, the security boundary). MCP and A2A are complementary layers: MCP connects an agent to *capabilities*; A2A connects an agent to *other agents* as black-box collaborators.

Architectural cautions for cross-boundary agent calls, whatever the protocol: treat a remote agent exactly like an untrusted tool with extreme output variance (its replies are injectable content — §2.2 poisoning applies); contract on **task semantics and artifacts**, never on behavior ("returns a report matching schema S", not "will reason carefully"); expect and design for *negotiation-style* failure (refusals, partials, clarifying questions are normal responses, not errors); and meter it — a remote agent's cost/latency is unbounded from your side, so budgets and timeouts are part of the contract.

---

## 11. Drift, Versioning & Change Management

Agent behavior is a function of **(model version × prompts × tool definitions × retrieval corpus × memory contents)** — five independently drifting inputs. Conventional software has one (code).

- **Model drift**: providers retire and update models; "same model ID" across a provider-side revision can shift behavior (instruction-following literalness, tool-trigger rates, verbosity have all shifted across recent model generations — prompts tuned to *overcome* an old model's weakness routinely *overtrigger* on its successor). Handle: pin model versions where offered; hold a **golden eval set** whose pass-rate is the regression gate for any model bump; budget a re-tuning pass (de-prescribing prompts) per migration rather than treating it as a string swap.
- **Prompt/tool-description versioning**: these are *behavioral code* — keep them in version control, deploy via the same gate as code (eval suite green), and record the prompt-bundle version in every run trace so production behavior is attributable to a version. A one-line tool-description edit can swing tool-selection rates double digits; untracked, that's an unexplainable production incident.
- **Silent-dependency drift**: the retrieval corpus (§6.3) and accumulated memory (§3.4) change behavior with zero deploys. The monitoring answer is the same for both: continuously-running evals against live state + drift alarms on key behavioral metrics (tool-call rate, mean steps per task, refusal rate, tokens per completed task). A step-function change in any of these *without a deploy* means a silent dependency moved.
- **Configuration as versioned artifacts**: hosted agent platforms make this first-class (immutable agent-config versions; sessions pin a version; rollback = repoint). Self-hosting, replicate the property: an immutable `agent_config@vN` (model + prompts + tool defs + parameters) that runs reference, traces record, and rollbacks restore. Mutable-in-place agent configs are the equivalent of editing code in production.

---

## 12. Debugging & Non-Reproducibility

The uncomfortable ground truth: **you cannot exactly reproduce an agent run.** Sampling is non-deterministic (and frontier reasoning models increasingly don't expose temperature at all), the world the tools touch has changed, and caches/corpora moved. Debugging therefore shifts from "reproduce the bug" to **"explain the trace"**:

- **Capture everything at the boundary**: the exact rendered request (post-assembly, post-truncation — not your template), the full response including thinking/tool blocks, tool inputs/outputs, timing, token usage, config version. The assembled-vs-template distinction matters: a large class of "model is dumb" bugs are *assembly* bugs (wrong doc injected, truncation ate the constraint, stale cache served) visible only in the rendered request.
- **Triage in fixed order** — where was the first divergence from expectation? (1) Was the right information *in context* at the failing step? (assembly/retrieval bug) → (2) Was the reasoning sound given that context? (capability/prompt bug) → (3) Was the tool call correct, and did the tool behave? (tool bug) → (4) Did earlier poisoned context cause it? (walk backward to the first wrong fact's entry point). Most teams jump straight to (2) and re-prompt; the majority of real faults live in (1), (3), and (4).
- **Counterfactual replay**: even without exact reproduction, you can re-run *from a checkpoint* with one variable changed (the fixed prompt, the corrected tool output) and see whether the trajectory repairs — checkpointing (§9.1) is a debugging tool, not just a reliability one.
- **Aggregate before anecdotes**: single-trace debugging finds mechanism; only N-trial runs distinguish "5% flake we ship with monitoring" from "deterministic bug". Failure-clustering over traces (group by first-divergence step / failing tool / error class) tells you which mechanism is *worth* finding.

---

## 13. Human–Agent Interaction

The interaction layer has its own failure modes, and they're product-architecture decisions:

- **Approval fatigue is a security failure, not a UX nit.** Gate too many actions and humans rubber-stamp — at which point the gate provides *negative* value (false assurance). Handle by gating on **reversibility and blast radius**, not on action count; batch related approvals into one reviewable plan ("about to: create branch, edit 3 files, open PR — approve set?"); auto-allow within pre-declared scopes ("anything under /sandbox") and escalate only on boundary crossings.
- **Trust calibration**: users either over-trust (accept fabricated progress — mitigate with evidence-grounded status, §4.2) or under-trust (re-check everything, erasing the productivity win — mitigate with calibrated confidence surfacing: the agent flags *which* outputs are verified vs. inferred, so attention goes where it's needed). The product goal is not maximum trust; it's *accurate* trust.
- **The interruption contract**: define — and tell the user — what "stop" means (finish the current write, then halt with a labeled state, §9.2), what gets rolled back, and what survives. Ambiguous interruption semantics produce both data corruption and user fear of the stop button.
- **Expectation setting for long turns**: minutes-long autonomous stretches are now normal; silent agents read as hung. Stream meaningful progress (phase transitions, findings — not tool-call noise), and make narration *derived from telemetry* where possible (§4.2) so progress reporting can't lie.
- **Escalation as a first-class outcome**: "I'm blocked, here's exactly why, here's what I need" must be a *successful* terminal state in your metrics and your prompts — agents optimized solely for completion learn to never escalate, which is how confident garbage ships. Reward (in evals) correct escalation as success, and audit the false-completion vs. unnecessary-escalation ratio as a product health metric.

---

## 14. Architectural Decision Records

The recurring trade-offs, compressed into the form you'd actually argue about in a design review:

**ADR-1: Where does the loop run?** Self-hosted loop (max control, every interception point, you own reliability §9) vs. framework (state graphs, checkpointing, tracing for free — at abstraction lock-in) vs. hosted runtime (loop, sandbox, sessions, versioned configs managed — at platform-primitive adoption). Decide on: how much you need custom interception (approvals, custom budgets) vs. how much undifferentiated reliability engineering you want to not own. The loop itself is trivial; **the surrounding reliability/control plane is the real build-vs-buy object.**

**ADR-2: Workflow vs. agent per route.** Revisit per *route*, not per product — production systems are workflow backbones with agentic sub-routes where enumeration genuinely fails. Misclassification cost is asymmetric: an unnecessary agent costs money, latency, and variance forever; an over-rigid workflow costs a redesign once. Default to workflow; promote on evidence.

**ADR-3: One agent vs. many.** Multi-agent buys context isolation, parallelism, and privilege separation; it costs the context-transfer problem (§8.2) and a token multiplier. The honest default: **one agent + good tools + sub-agent offloading for context isolation**, going truly multi-agent only when parallelism or privilege boundaries demand it. Specialization alone is usually achievable with prompts/tool-subsets inside one agent.

**ADR-4: Memory store choice.** Files (debuggable, agent-curated, small scale) vs. vector (scales, weak updates, needs reconciliation) vs. temporal graph (supersession first-class, highest cost) vs. paged core/archival (self-managed working set). Choose by which of the four memory problems (§3.1) dominates; hybridize freely; the unforgivable error is having no write/update/forget policy at all.

**ADR-5: Where verification spends.** Programmatic checks everywhere they're possible; fresh-context verifier agents at integration points; adversarial verification reserved for high-stakes claims. Decide the verification token budget (≈10–30% of run spend) explicitly — implicit verification budgets collapse to zero under cost pressure, and that's when silent failures ship.

**ADR-6: Synchronous vs. event-driven control plane.** Request/response is fine for short interactive sessions; anything long-running, interruptible, steerable, or multi-consumer wants an **event-stream architecture** (session = append-only event log; UI, harness, audit, and resume logic are all consumers). Retrofitting interruption and resume onto request/response is consistently more expensive than starting event-driven.

**ADR-7: Trust boundaries before topology.** Draw the untrusted-content / private-data / egress map (the trifecta) *first*, then place agents and tools inside the compartments — topology chosen for capability reasons and patched for security afterward is how confused deputies (§10.1) ship. Privilege separation is a legitimate, sometimes sufficient, reason to go multi-agent on its own.

---

## Appendix — Challenge → Section Index

| You're seeing... | Go to |
|---|---|
| Agent degrades over long sessions, repeats itself | §2.1–2.3 |
| Agent treats its own earlier mistake as fact | §2.2 (poisoning), §3.4 (memory poisoning) |
| Old and new versions of a fact both being used | §2.2 (clash), §3.2-D (supersession) |
| "It stopped following the system prompt" | §2.4 |
| Remembers wrong/stale things across sessions | §3.2, §3.4 |
| Declares done, work isn't | §4.2 |
| Stuck repeating a failing action | §4.2 |
| Status updates don't match reality | §4.2, §13 |
| Picks the wrong tool / doesn't use the tool | §5.1 |
| Plausible-but-wrong tool arguments | §5.2 |
| Duplicate side effects (double-charge class) | §5.4, §9.1 |
| RAG answers got worse, nothing was deployed | §6.3, §11 |
| Stale/deleted docs still being cited | §6.1 |
| MCP tool broke after a server update | §7 |
| Sub-agent solved the wrong problem well | §8.2 |
| Parallel workers clobbering each other | §8.3 |
| Wrong sub-result accepted and integrated | §8.4 |
| Crash mid-run, can't safely resume | §9.1 |
| Retry storms across the fleet | §9.3 |
| "The agent did it" dead-ends the audit | §10.1 |
| Behavior changed after a model upgrade | §11 |
| Can't reproduce a production failure | §12 |
| Users rubber-stamping approvals | §13 |
