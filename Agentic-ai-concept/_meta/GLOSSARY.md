# Glossary — canonical definitions

The single source of truth for terms used across the guide. Sections link here instead of
re-defining. Ordered roughly foundational → advanced.

### Core
- **Token** — the atomic unit an LLM reads/writes; a sub-word fragment (~3–4 chars of English on
  average). Billing, context limits, and latency are all measured in tokens, not words. See [§02](../02-LLM-Fundamentals/).
- **Context window** — the maximum number of tokens (input + output) a model can attend to in one
  request. A hard limit *and* a soft quality cliff (see *context rot*).
- **Context rot** `[Established]` — measurable degradation in retrieval/reasoning quality as the used
  context grows, even below the hard limit. Why "just stuff everything in" fails.
- **Embedding** — a fixed-length vector encoding the *meaning* of text so that semantic similarity ≈
  geometric closeness. The substrate of vector search and RAG.
- **Inference** — a single forward pass (or generation) of the model; the runtime act of "running"
  the LLM. Distinct from *training*.
- **Prefill vs. decode** — the two phases of inference. *Prefill* processes the prompt (compute-bound,
  parallel); *decode* emits tokens one at a time (memory-bandwidth-bound, sequential). They have
  different cost/latency characteristics; see [§18](../18-Performance-Optimization/).
- **KV cache** — cached key/value attention tensors from prior tokens so each new token doesn't
  recompute the whole sequence. The reason long outputs are cheaper per-token than they "should" be,
  and the thing *prompt caching* exposes to you.

### Agents
- **Agent** — an LLM operating in a **loop** with **tools**, optional **memory**, and a **stopping
  condition**, given autonomy to choose its next action. Contrast with a fixed pipeline. See [§03](../03-Agent-Architecture/).
- **Agent loop** — the think → act → observe cycle: model proposes an action (often a tool call),
  the environment executes it, the result is fed back, repeat until done.
- **Workflow** — an LLM application where steps are orchestrated by **code on predefined paths**.
  Agents choose their own path; workflows follow yours. The choice between them is foundational —
  see [§10](../10-Orchestration/) and the decision matrix in [§03](../03-Agent-Architecture/).
- **Autonomy level** — how much the agent decides vs. follows a script (L0 fixed prompt → L5 fully
  autonomous goal-seeking). See [§03](../03-Agent-Architecture/).
- **Trajectory** — the full ordered sequence of (thought, action, observation) steps an agent took
  for one task. The primary unit of *agent evaluation* and *debugging*. See [§16](../16-Evaluation/).
- **Tool / function calling** — the model emits a structured request (name + JSON args) that your
  code executes, returning a result the model reads. The bridge between "talking" and "doing." See [§05](../05-Tools-and-Function-Calling/).
- **System prompt** — the persistent instruction block defining the agent's identity, constraints,
  and output contract; highest-trust text in the request. See [§04](../04-System-Prompts/).
- **ReAct** — *Reason + Act*: interleave free-form reasoning with tool calls in the loop. The default
  single-agent pattern. See [§11](../11-Single-Agent-Patterns/).
- **Reflection / Reflexion** — the agent critiques its own output/trajectory and retries, optionally
  storing the critique as memory. See [§09](../09-Planning/), [§11](../11-Single-Agent-Patterns/).

### Knowledge & memory
- **RAG** (Retrieval-Augmented Generation) — inject retrieved, source-of-truth context into the
  prompt at inference time to ground answers and reduce hallucination. See [§08](../08-RAG/).
- **Chunking** — splitting source documents into retrieval units. The single highest-leverage RAG
  decision. See [§08](../08-RAG/).
- **Re-ranking** — a second, more precise relevance scoring pass over first-stage retrieval hits
  (cross-encoder or LLM). Trades latency for precision. See [§08](../08-RAG/).
- **Hybrid search** — combining lexical (BM25) + dense (vector) retrieval, fused (e.g., RRF). Beats
  either alone on most corpora. See [§08](../08-RAG/).
- **Graph RAG** — retrieval over a knowledge graph of entities/relations rather than (or with) flat
  chunks; strong for multi-hop and "global" questions. See [§08](../08-RAG/).
- **Agentic RAG** — retrieval driven by an agent that decides *whether*, *what*, and *how many times*
  to retrieve, instead of a single fixed query. See [§08](../08-RAG/).
- **Short-term / working memory** — what's in the current context window for this task.
- **Long-term memory** — persisted across sessions (often in a vector/SQL/graph store).
- **Episodic memory** — records of specific past events/interactions ("on 2026-03-02 the user said…").
- **Semantic memory** — distilled facts/knowledge independent of when they were learned.
- **Memory poisoning** `[Established threat]` — an attacker (or the agent itself) writes false/malicious
  content into long-term memory that corrupts future behavior. See [§07](../07-Memory/), [§14](../14-Agent-Security/).

### Protocols & interop
- **MCP** (Model Context Protocol) — an open, JSON-RPC-2.0-based protocol (Anthropic, 2024) that
  standardizes how applications expose **tools**, **resources**, and **prompts** to LLMs. "USB-C for
  AI tools." See [§06](../06-MCP/).
- **A2A** (Agent-to-Agent) — a protocol for agents (across vendors/orgs) to discover and delegate to
  one another. Complementary to MCP (agent↔agent vs. agent↔tools). See [§13](../13-Agent-Communication/), [§26](../26-Future-Trends/).
- **Tool / Resource / Prompt** (MCP primitives) — *tools* are model-invoked actions; *resources* are
  application-attached data; *prompts* are user-invoked templates. See [§06](../06-MCP/).

### Operations
- **Guardrail** — a deterministic or model-based check on inputs, outputs, or tool calls that enforces
  safety/policy outside the LLM's discretion. See [§15](../15-Guardrails/).
- **Prompt injection** `[Established threat]` — untrusted content (user input or retrieved data)
  manipulates the model into ignoring its instructions. *Direct* (user) vs. *indirect* (via tools/RAG).
  The #1 agent security risk. See [§14](../14-Agent-Security/).
- **LLM-as-judge** — using an LLM to score outputs/trajectories against a rubric, for eval at scale.
  See [§16](../16-Evaluation/).
- **Span / trace** — observability primitives; a *span* is one operation (an LLM call, a tool call),
  a *trace* is the tree of spans for one request. OpenTelemetry has GenAI semantic conventions for
  these. See [§17](../17-Observability/).
- **Prompt caching** — vendor feature that caches the KV-state of a stable prompt prefix so repeated
  calls skip re-processing it; major latency & cost win. See [§18](../18-Performance-Optimization/), [§21](../21-Cost-Optimization/).
- **Semantic caching** — returning a cached response when a *new* query is semantically close to a
  prior one (vector similarity), vs. exact-match caching. See [§18](../18-Performance-Optimization/).
