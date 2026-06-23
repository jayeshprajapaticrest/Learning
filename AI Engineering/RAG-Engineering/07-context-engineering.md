# Module 7 — Context Engineering

> Retrieval finds the evidence; **context engineering decides what the model actually sees and in what order.** Great retrieval wasted by sloppy context assembly is one of the most common (and invisible) ways RAG underperforms. This is where "prompt engineering" meets "information packing."

---

## 1. Why it matters

The LLM's context window is a **scarce, non-uniform resource**:

- **It's finite and costly.** Every retrieved token costs money and latency, and dilutes attention.
- **It's positionally biased.** "Lost in the Middle" (Liu et al., 2023, arXiv:2307.03172) shows models use information at the **beginning and end** of the context far better than the middle. Order matters — a lot.
- **More context is not better.** Stuffing 50 chunks often *lowers* accuracy vs. 5 well-chosen, well-ordered ones (distraction, contradiction, and middle-loss). Long-context models help but don't eliminate this.
- **Garbage/contradictory context induces hallucination** and reduces faithfulness.

Context engineering is the discipline of assembling the **minimum, highest-signal, best-ordered** evidence plus the right instructions so the model answers correctly and citably.

---

## 2. Core concepts & techniques

### Context assembly pipeline
```
Reranked candidates → dedup/near-dup removal → (optional) compression/summarization
   → ordering (most-relevant at edges) → token-budget enforcement
   → prompt template (system + instructions + context + citations format + query)
```

### Key techniques
- **Reordering for position bias.** After reranking, place the most relevant passages at the **start and end**, least relevant in the middle ("lost-in-the-middle reordering"; LangChain `LongContextReorder`, LlamaIndex has an equivalent). Cheap, measurable win.
- **Context (contextual) compression.** Filter/condense retrieved text to only query-relevant sentences before sending to the LLM. Approaches: extractive filtering (embeddings/cross-encoder per sentence), **LLMLingua / LongLLMLingua** prompt compression (Jiang et al., Microsoft, arXiv:2310.05736 / 2310.06839), and LangChain `ContextualCompressionRetriever`. Cuts tokens/cost and reduces distraction.
- **Deduplication** of near-identical chunks (common with overlap or duplicate sources) to avoid wasting budget and biasing the model.
- **Small-to-big / parent expansion** (from Module 2): retrieve precise small chunks, then *expand* to their parent/neighbors for the LLM so it has coherent context.
- **Structured context formatting.** Clearly delimit each source (e.g., numbered with IDs/metadata) so the model can **cite** and so you can post-validate citations. Include source metadata (title, date, URL) the user needs.
- **Instructions & grounding constraints.** Tell the model to answer **only** from context, to say "I don't know" when evidence is absent, and to cite source IDs. This is the main lever against hallucination/over-claiming.
- **Token budget management.** Allocate the window deliberately: system/instructions, N context tokens, room for the answer; truncate/compress to fit with margin.
- **Prompt caching** (Anthropic/OpenAI): cache stable prefixes (system prompt, long static context, tool defs) to cut cost/latency on repeated calls — see Module 9. When using Claude, structure the prompt so the cacheable parts come first.

### "Context engineering" for agents (the broader meaning)
Beyond RAG prompt assembly, the term now covers managing the *entire* working context of an agent over time: what to retrieve, retain, summarize, or evict from memory across steps. Primary reference: **Anthropic — "Effective context engineering for AI agents"** (docs.claude.com / Anthropic engineering blog). Relevant when RAG is embedded in a multi-step agent.

---

## 3. Learning path

### Beginner
- Read "Lost in the Middle." Implement reordering after reranking; measure answer-quality change.
- Write a strong grounded prompt: "answer only from sources, cite IDs, say I-don't-know." Compare faithfulness with/without it.

### Intermediate
- Implement **contextual compression** (extractive filtering) and **dedup**; measure token savings vs. quality.
- Implement **citation formatting** + a post-check that every cited ID was actually in context.
- Implement small-to-big parent expansion.

### Advanced
- Add **LLMLingua-style prompt compression** for long contexts; quantify the cost/quality frontier.
- Build a **token-budget allocator** that adapts k and compression based on query complexity and model window.
- Tune context size empirically (find the k where adding chunks stops helping / starts hurting on your eval set).

### Expert
- Design **adaptive context policies** in an agentic loop: dynamic memory, summarization of prior steps, eviction, and prompt-caching-aware prompt layout.
- Build automatic **faithfulness/citation verification** in the generation step (claim → supporting source check).

---

## 4. Best resources

- **Papers:** Lost in the Middle (2307.03172); LLMLingua / LongLLMLingua (2310.05736 / 2310.06839); RECOMP context compression (Xu et al., 2023, arXiv:2310.04408); Self-RAG (2310.11511) for grounded/self-critique generation.
- **Docs/blogs:** Anthropic *"Effective context engineering for AI agents"* and prompt-engineering + prompt-caching docs (docs.claude.com); OpenAI prompting & prompt-caching docs; LangChain `LongContextReorder` & `ContextualCompressionRetriever` docs; LlamaIndex node-postprocessors (reorder, compress, dedup) docs.
- **Repos:** `microsoft/LLMLingua`, `langchain-ai/langchain` (postprocessors), `run-llama/llama_index` (node postprocessors).

---

## 5. Production architecture patterns

- **Postprocessor chain** between reranker and generator: dedup → compress → reorder → budget-trim → format.
- **Cacheable prompt layout:** static system/instructions + (optionally cached) stable context first; volatile query last (maximizes prompt-cache hits).
- **Citation contract:** enforce a structured source block and validate citations post-generation; reject/repair uncited claims.
- **Grounding guardrails:** "answer only from context" + abstention path + an output check for unsupported claims.
- **Per-query budget tiers** tied to the router (simple queries → small context; hard → larger/compressed).

---

## 6. Common mistakes & anti-patterns

- **Dumping top-k in arbitrary order** (ignoring position bias).
- **"More context = better"** — over-stuffing degrades accuracy and inflates cost/latency.
- **No "I don't know" path** → the model fabricates when evidence is missing.
- **No citation/grounding instruction** → unattributable, untrustworthy answers.
- **Duplicate/near-dup chunks** crowding the window and biasing the model.
- **Compressing away the actual answer** with too-aggressive filtering — measure faithfulness, not just token savings.
- **Volatile content before stable content** in the prompt → zero prompt-cache hits, needless cost.
- **Ignoring the model's real effective context** (advertised window ≠ where it reads well).

---

## 7. Interview-level expectations

- Explain "lost in the middle" and the concrete mitigations (reorder, fewer/better chunks, compression).
- Explain why more retrieved context can *hurt* answer quality and cost.
- Explain contextual compression and the token-vs-quality trade-off.
- Explain how you'd force grounded, cited answers and verify citations.
- Explain prompt layout for prompt caching and why it matters at scale.

---

## 8. Enterprise-scale considerations

- **Cost:** context tokens are usually the dominant generation cost; compression + caching are major savings levers.
- **Latency:** large contexts increase TTFT/decode time; trim aggressively.
- **Compliance:** citations and provenance in the assembled context are often a hard requirement; redact PII before it enters the prompt.
- **Determinism/auditability:** log the *exact* assembled context per request for debugging and eval-data harvesting.
- **Safety:** retrieved context is untrusted — strip/escape instructions in retrieved text to mitigate indirect prompt injection.

---

## 9. Trade-offs & decision framework

```
Answers ignoring clearly-retrieved facts?     → reorder (put key passages at edges); reduce k.
Cost/latency too high from context tokens?     → contextual compression + dedup + smaller k + caching.
Model hallucinating beyond sources?            → grounding instructions + "I don't know" + citation checks.
Precise match but missing surrounding context? → small-to-big / parent expansion.
Repeated calls share a big static context?     → prompt caching with stable-prefix layout.

Find the "knee": increase k until eval quality stops improving — that's your context size, not the max window.
```

---

## 10. Real-world use cases

- **Cited enterprise assistants** — strict grounding + citation contracts (legal/finance/health).
- **High-volume support bots** — compression + prompt caching to control cost at scale.
- **Long-document QA** — small-to-big + reorder to handle large sources within budget.
- **Agentic copilots** — dynamic context/memory management across multi-step tasks.

---

## 11. Essential vs optional

- **Essential:** position-aware ordering, grounding/citation instructions + abstention, token-budget management, dedup.
- **High-ROI:** contextual compression, prompt caching, small-to-big expansion.
- **Optional / situational:** LLMLingua-style heavy compression, adaptive agentic context policies — at scale or in agent settings.

---

### Capstone project for this module
Hold retrieval fixed and vary only context engineering: (1) baseline top-k unordered, (2) + reorder, (3) + dedup + compression, (4) + strict grounding/citation prompt. Measure faithfulness, answer correctness, tokens/query, and p95 latency for each. Show that context engineering alone moves the metrics meaningfully — and find your optimal k.
