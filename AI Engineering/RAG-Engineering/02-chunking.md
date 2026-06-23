# Module 2 — Chunking (Smart, Component-Aware, Semantic)

> "Your retrieval is only as good as your chunks." Chunking is the cheapest stage to get wrong and one of the highest-impact to get right. It is upstream of *everything* — bad chunks cap the ceiling of every downstream technique.

---

## 1. Why it matters

An LLM never sees your documents — it sees **chunks**. The chunk is the atomic unit of retrieval. If a chunk splits a table from its header, severs a sentence mid-thought, or bundles three unrelated topics, then:

- Embeddings become **diluted/averaged** (one vector trying to represent multiple ideas → poor similarity).
- Retrieval returns **partial or context-free** fragments.
- The LLM gets **incoherent evidence** and either hallucinates or refuses.

Chunking decisions also dictate **recall vs. precision vs. cost**: small chunks → precise but fragmented; large chunks → coherent but noisy and token-expensive. Mastering chunking is mastering this trade-off per data type.

---

## 2. The chunking spectrum (simplest → smartest)

| Strategy | How | Pros | Cons |
|----------|-----|------|------|
| **Fixed-size (char/token)** | Split every N tokens | Trivial, fast | Cuts mid-sentence; ignores structure |
| **Fixed-size + overlap** | N tokens, M-token overlap | Reduces boundary loss | Duplication; still structure-blind |
| **Recursive character splitting** | Split on a priority list of separators (`\n\n` → `\n` → `. ` → ` `) | Respects natural boundaries; the sane default | Heuristic; no semantics |
| **Document/structure-aware (component-aware)** | Split on document structure: markdown headers, HTML tags, code AST, tables, slides | Preserves logical units & hierarchy | Needs per-format parsers |
| **Semantic chunking** | Split where embedding similarity between adjacent sentences drops | Topically coherent chunks | Compute cost; tunable threshold; not always better |
| **Proposition / atomic** | Decompose into standalone factual statements (LLM-generated) | Very high precision | Expensive (LLM per doc); can lose context |
| **Hierarchical (small-to-big / RAPTOR)** | Index small, retrieve, expand to parent / summary tree | Best of both: precise match, rich context | More moving parts |

### Component-aware chunking (deep dive)
"Component-aware" = the splitter understands the *document's components* and never splits across the wrong boundary:

- **Markdown:** split by header hierarchy; carry the header path (`# Guide > ## Auth > ### OAuth`) into each chunk's metadata and text. (LangChain `MarkdownHeaderTextSplitter`, LlamaIndex `MarkdownNodeParser`.)
- **HTML:** split by semantic tags (`<section>`, `<article>`, headers).
- **Code:** split along the **AST** (function/class boundaries), not raw lines. (LangChain code splitters use language-aware separators; LlamaIndex `CodeSplitter` uses tree-sitter.)
- **Tables:** keep a table intact; attach its caption/header. Consider serializing each row with column headers, or summarizing the table for the embedded text while keeping the raw table for the LLM.
- **PDFs / complex layouts:** use a layout-aware parser (e.g., `unstructured`, or layout models) to recover reading order, headings, lists, and tables *before* chunking. Garbage parsing → garbage chunks no strategy can fix.

### Semantic chunking (deep dive)
Embed sentences, walk through the document, and start a new chunk when the cosine distance between consecutive sentences (or a rolling window) exceeds a threshold (e.g., the 95th percentile of distances). Implementations: LlamaIndex `SemanticSplitterNodeParser`, LangChain `SemanticChunker`. **Reality check:** the empirical literature (incl. Wang et al. 2024, arXiv:2407.01219, and various vendor benchmarks) shows semantic chunking is *not* a guaranteed win over good recursive/structural chunking and costs more. Use it where documents lack clear structure and topics shift mid-paragraph; always A/B it on your eval set.

### Contextual chunking (Anthropic — strongly recommended)
**Anthropic's "Contextual Retrieval"** (<https://www.anthropic.com/news/contextual-retrieval>, 2024): before embedding each chunk, prepend a short LLM-generated blurb situating the chunk within the whole document (e.g., "This chunk is from the Q3 2023 10-K, Risk Factors section, discussing supply-chain risk."). Anthropic reports large drops in retrieval failure when combined with hybrid search + reranking. Use **prompt caching** of the full document to make the per-chunk LLM calls cheap. This is one of the highest-ROI chunking upgrades available today.

---

## 3. Learning path

### Beginner
- Implement fixed-size + overlap and recursive splitting by hand; visualize the chunk boundaries.
- Read LangChain's [text splitters conceptual docs](https://python.langchain.com/docs/concepts/text_splitters/) and LlamaIndex node-parser docs.
- Internalize the recall/precision trade-off of chunk size.

### Intermediate
- Build **component-aware** splitters for your real data types (markdown + code + tables).
- Use `unstructured` (<https://docs.unstructured.io>) or a layout parser for PDFs; inspect parse quality.
- Add header-path metadata to every chunk.

### Advanced
- Implement **semantic chunking** and **small-to-big / parent-document retrieval** (LlamaIndex `AutoMergingRetriever` / `SentenceWindowNodeParser`; LangChain `ParentDocumentRetriever`).
- Implement **Anthropic Contextual Retrieval** with prompt caching.
- Build **RAPTOR** (recursive summary tree, arXiv:2401.18059).

### Expert
- Treat chunking as a **tunable hyperparameter sweep** driven by your eval harness: grid over size × overlap × strategy per document class, pick by retrieval metrics, not intuition.
- Build a per-document-type chunking router (a 10-K is chunked differently than a chat transcript or a code file).

---

## 4. Best resources

- **Papers:** RAPTOR (2401.18059); "Dense X Retrieval: What Retrieval Granularity Should We Use?" / proposition retrieval (Chen et al., 2023, arXiv:2312.06648); Best-Practices (2407.01219) for chunk-size ablations.
- **Blogs:** Anthropic *Contextual Retrieval*; Pinecone *"Chunking Strategies for LLM Applications"*; Greg Kamradt's *"5 Levels of Text Splitting"* (notebook + talk) — excellent intuition builder; LlamaIndex blog on node parsing and small-to-big.
- **Docs:** LangChain text-splitters; LlamaIndex node parsers / metadata extractors; `unstructured` docs.
- **Repos:** `Unstructured-IO/unstructured`, `run-llama/llama_index` (node parsers), `FullStackRetrieval-com/RetrievalTutorials` (Greg Kamradt's chunking notebooks).

---

## 5. Production architecture patterns

- **Parse → normalize → chunk → enrich → embed** as a pipeline with the parse step isolated and monitored (most quality loss is here).
- **Carry hierarchy in metadata**: `doc_id`, `section_path`, `page`, `chunk_index`, `prev/next_chunk_id`. Enables parent expansion, neighbor windowing, and citation.
- **Stable chunk IDs** (hash of content + position) for idempotent incremental re-indexing.
- **Dual representation**: store a clean embedded text (possibly contextualized/summarized) *and* the raw, richer text given to the LLM. The thing you embed need not equal the thing you show the model.

---

## 6. Common mistakes & anti-patterns

- **One global chunk size for all document types.** A code file, a contract, and a chat log need different strategies.
- **Splitting tables, code blocks, or lists mid-structure.**
- **Zero overlap with fixed-size chunking** → key sentences land on boundaries and vanish.
- **Over-chunking** (tiny chunks) → fragments with no context; the LLM can't reason.
- **Under-chunking** (huge chunks) → diluted embeddings, low precision, wasted tokens.
- **Embedding raw OCR/HTML garbage** because the parse step was skipped.
- **Adopting semantic chunking because it sounds smart**, without A/B evidence it beats recursive on *your* data.

---

## 7. Interview-level expectations

- Explain the recall/precision/cost trade-off of chunk size and how you'd choose empirically.
- Compare fixed/recursive/semantic/structural chunking and when each fits.
- Explain small-to-big / parent-document retrieval and *why* it helps (match precisely, generate with context).
- Explain why the embedded text and the LLM-provided text can differ (Contextual Retrieval, summary-indexing).
- Describe how chunk metadata enables filtering, citation, and parent expansion.

---

## 8. Enterprise-scale considerations

- **Cost of contextual/semantic chunking at scale** — millions of docs × an LLM call per chunk is real money; use prompt caching, batch APIs, and smaller models for the context step.
- **Reproducibility & versioning** — chunking config is part of your index version; changing it invalidates the index. Record it.
- **Throughput** — parsing/OCR is often the ingestion bottleneck; parallelize and queue.
- **PII** — detect/redact during the chunk/enrich step before embeddings leave your boundary.

---

## 9. Trade-offs & decision framework

```
Is the document well-structured (markdown/HTML/code/clear headings)?
  → YES: structure/component-aware splitting (+ header metadata). Often enough.
  → NO : recursive splitting baseline; consider semantic chunking IF eval shows topic-bleed problems.

Do you need both precise matching AND rich generation context?
  → small-to-big / parent-document / sentence-window.

Are retrieved chunks losing whole-doc context (ambiguous pronouns, "the company", "this section")?
  → Anthropic Contextual Retrieval (prepend context before embedding).

Are questions "global" (themes across the whole corpus)?
  → RAPTOR summary tree, or GraphRAG (Module 6).
```

Default starting point: **recursive/structural splitting, ~256–512 tokens, ~10–20% overlap, header metadata** — then tune against eval.

---

## 10. Real-world use cases

- **Technical docs / API references** → markdown-header chunking with the header path embedded.
- **Codebases** → AST/function-level chunking for code Q&A and coding assistants.
- **Financial filings / contracts** → layout-aware parsing + section-aware chunking + table preservation; Contextual Retrieval shines here.
- **Support transcripts / chat logs** → turn-aware or semantic chunking.

---

## 11. Essential vs optional

- **Essential:** recursive + structural/component-aware chunking, overlap, header metadata, decent PDF parsing.
- **High-ROI:** small-to-big retrieval, Anthropic Contextual Retrieval.
- **Optional / situational:** semantic chunking, proposition chunking, RAPTOR — adopt only with eval evidence.

---

### Capstone project for this module
Take one messy real corpus (PDFs with tables) and benchmark 4 chunking strategies on a fixed eval set (recall@k, nDCG, answer faithfulness). Produce a chart of quality vs. chunk size and a written recommendation. You will never again chunk by intuition.
