# 02 — Document Ingestion Pipelines (PDF, DOCX, OCR, Images)

> **Goal:** Turn messy enterprise files — born-digital PDFs, scanned contracts, DOCX,
> spreadsheets, images — into clean, structured, chunk-ready text with reliable
> metadata. **This is where RAG quality is won or lost.** Garbage in, garbage out.

---

## 1. Why ingestion is the hard part

A demo loads one clean PDF. Production loads 200,000 files where:

- Half the PDFs are **scans** (images of text) → need OCR.
- Tables are **visually** structured but semantically scrambled by naive extractors.
- Multi-column layouts get read **left-to-right across columns** → word salad.
- Headers/footers/page numbers leak into every chunk as noise.
- The same logical document arrives as PDF, DOCX, and email attachment.

Your job: a pipeline that's **robust** (never crashes the batch on one bad file),
**structure-preserving** (keeps headings/tables/reading order), and **observable**
(you know what failed and why).

### Pipeline architecture

```
 source (T08: SharePoint/S3/CRM)
        │
        ▼
 ┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
 │ 1. DETECT   │──►│ 2. EXTRACT   │──►│ 3. CLEAN &    │──►│ 4. CHUNK     │
 │ type, scan? │   │ text+layout, │   │   NORMALIZE   │   │ (T01) + meta │
 │ lang, pages │   │  OCR if scan │   │ dedupe noise  │   │              │
 └─────────────┘   └──────────────┘   └───────────────┘   └──────────────┘
        │                 │                                       │
        ▼                 ▼                                       ▼
   quarantine        OCR fallback                        5. EMBED + INDEX (T03)
   on failure        on low text yield                   + PII scan (T09)
```

Make every stage **idempotent** and keyed by a **content hash**, so re-running skips
unchanged files and you can reprocess a single document without rebuilding the corpus.

---

## 2. Detect first — don't assume

Route each file by type and whether it needs OCR. The cheapest correct path beats one
heavy parser for everything.

```python
import hashlib, fitz  # PyMuPDF
from pathlib import Path

def file_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pdf_needs_ocr(path: Path, min_chars_per_page: int = 100) -> bool:
    """If a PDF yields almost no extractable text, it's a scan → OCR."""
    doc = fitz.open(path)
    sample = min(5, len(doc))
    chars = sum(len(doc[i].get_text("text")) for i in range(sample))
    return (chars / max(sample, 1)) < min_chars_per_page
```

| Extension | Born-digital path | Scanned/image path |
|-----------|-------------------|--------------------|
| `.pdf` | PyMuPDF / Docling / Unstructured | OCR (Tesseract / cloud DI) |
| `.docx`, `.pptx` | python-docx / Unstructured | n/a |
| `.xlsx`, `.csv` | pandas / openpyxl → markdown tables | n/a |
| `.png`, `.jpg`, `.tiff` | n/a | OCR |
| `.html`, `.md`, `.txt` | direct | n/a |
| `.eml`, `.msg` | email parser + attachment recursion | per-attachment |

---

## 3. Extraction strategies

### 3.1 Born-digital PDF — fast path with PyMuPDF

```python
import fitz

def extract_pdf_text(path) -> list[dict]:
    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc):
        # "blocks" preserves reading order better than raw "text" for multi-column
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1]), b[0]))   # sort by (y, x)
        text = "\n".join(b[4] for b in blocks if b[4].strip())
        pages.append({"page": i + 1, "text": text})
    return pages
```

### 3.2 Layout-aware extraction — Docling / Unstructured (recommended for RAG)

These understand document *structure*: titles, paragraphs, lists, tables, reading
order. They emit typed **elements** you can chunk intelligently (this is what powers the
structure-aware chunking in [T01 §2.3](01-rag-pipelines.md)).

**Docling** (strong on tables/layout, exports clean Markdown):

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("contract.pdf")
markdown = result.document.export_to_markdown()   # headings, tables preserved
# feed `markdown` straight into MarkdownHeaderTextSplitter (T01)
```

**Unstructured** (broadest format coverage, element-typed output):

```python
from unstructured.partition.auto import partition

elements = partition(filename="report.pdf", strategy="hi_res",  # hi_res = layout model + OCR
                     infer_table_structure=True, languages=["eng"])
for el in elements:
    print(el.category, "→", el.text[:80])   # Title, NarrativeText, Table, ListItem, ...
```

Element-aware chunking keeps a table or a list as **one** chunk instead of splitting it
mid-row:

```python
from unstructured.chunking.title import chunk_by_title
chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=200)
```

### 3.3 DOCX, PPTX, spreadsheets

```python
# DOCX — Unstructured handles styles/headings; python-docx for fine control
from unstructured.partition.docx import partition_docx
elements = partition_docx(filename="policy.docx")

# Spreadsheets — convert each sheet to a markdown table so the LLM can read it
import pandas as pd
def xlsx_to_markdown(path) -> str:
    out = []
    for name, df in pd.read_excel(path, sheet_name=None).items():
        out.append(f"## Sheet: {name}\n\n{df.to_markdown(index=False)}")
    return "\n\n".join(out)
```

---

## 4. OCR for scans and images

When text extraction yields little (§2), run OCR. Quality ranges from free/local to
cloud services that also recover layout and tables.

### 4.1 Local OCR — Tesseract / RapidOCR (free, on-prem, private)

```python
import fitz
from PIL import Image
import pytesseract, io

def ocr_pdf(path, dpi=300, lang="eng") -> list[dict]:
    doc = fitz.open(path)
    out = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)                 # higher DPI = better OCR, slower
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang=lang)
        out.append({"page": i + 1, "text": text})
    return out
```

Practical OCR tips that materially improve accuracy:
- **Render at 300 DPI** (150 is too low, 600 is wasteful).
- **Deskew & binarize** crooked scans (OpenCV) before OCR.
- **Set the language(s)** explicitly; multi-lingual docs need `lang="eng+fra"`.
- **`rapidocr-onnxruntime`** is a fast, dependency-light alternative to Tesseract.

### 4.2 Cloud Document Intelligence (best accuracy, handles tables + forms)

For high-value or messy docs (contracts, invoices, forms), managed services recover
**tables, key-value pairs, and layout** far better than local OCR:

- **Azure AI Document Intelligence** (great for enterprise, prebuilt invoice/receipt models)
- **AWS Textract** (forms + tables)
- **Google Document AI**

```python
# Azure AI Document Intelligence — layout model returns structured content
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

client = DocumentIntelligenceClient(endpoint=ENDPOINT, credential=AzureKeyCredential(KEY))
with open("invoice.pdf", "rb") as f:
    poller = client.begin_analyze_document("prebuilt-layout", body=f)
result = poller.result()
for table in result.tables:
    ...  # reconstruct rows/cols → markdown table for the chunk
```

### 4.3 VLM extraction (the modern option)

Multimodal LLMs (Claude with vision, etc.) can read a page image directly and return
clean structured Markdown — strong on complex layouts, charts, and handwriting. More
expensive per page than OCR; use it for the hard tail of documents that OCR mangles.

```python
import base64
def page_image_to_markdown(png_bytes: bytes, client) -> str:
    b64 = base64.standard_b64encode(png_bytes).decode()
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=4096,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": "Transcribe this page to clean Markdown. Preserve tables, headings, and reading order. Do not add commentary."},
        ]}],
    )
    return msg.content[0].text
```

---

## 5. Clean & normalize

Raw extraction is noisy. Clean **before** chunking so noise doesn't pollute embeddings:

```python
import re

def clean(text: str) -> str:
    text = re.sub(r"-\n(\w)", r"\1", text)          # de-hyphenate line-wrapped words
    text = re.sub(r"[ \t]+", " ", text)              # collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)           # collapse blank lines
    return text.strip()

def strip_repeating_headers_footers(pages: list[dict]) -> list[dict]:
    """Lines that appear on >60% of pages are almost always headers/footers."""
    from collections import Counter
    line_counts = Counter()
    for p in pages:
        for line in set(p["text"].splitlines()):
            line_counts[line.strip()] += 1
    boilerplate = {l for l, c in line_counts.items() if l and c > 0.6 * len(pages)}
    for p in pages:
        p["text"] = "\n".join(l for l in p["text"].splitlines() if l.strip() not in boilerplate)
    return pages
```

Also normalize: Unicode (`unicodedata.normalize("NFKC", ...)`), smart quotes, ligatures,
and detect language (`langdetect`/`fasttext`) to store as metadata for routing.

---

## 6. Robustness: the part that separates demos from production

```python
from dataclasses import dataclass, field
import logging

@dataclass
class IngestResult:
    doc_id: str
    status: str                      # "ok" | "ocr_fallback" | "quarantined"
    pages: int = 0
    chunks: int = 0
    errors: list[str] = field(default_factory=list)

def ingest_one(path) -> IngestResult:
    doc_id = file_fingerprint(path)
    res = IngestResult(doc_id=doc_id, status="ok")
    try:
        if path.suffix == ".pdf" and pdf_needs_ocr(path):
            pages, res.status = ocr_pdf(path), "ocr_fallback"
        else:
            pages = extract_pdf_text(path)
        pages = strip_repeating_headers_footers(pages)
        text = clean("\n\n".join(p["text"] for p in pages))
        if len(text) < 50:
            raise ValueError("near-empty extraction")        # likely a bad scan
        res.pages = len(pages)
        # → chunk (T01), PII-scan (T09), embed + index (T03)
    except Exception as e:                                    # never let one file kill the batch
        logging.exception("ingest failed: %s", path)
        res.status, res.errors = "quarantined", [str(e)]
    return res
```

Non-negotiables for a real pipeline:

- **Quarantine, don't crash.** One corrupt file must not fail the batch. Route failures
  to a dead-letter queue with the error for human review.
- **Idempotency via content hash.** Skip unchanged files; reprocess only what changed.
- **Incremental sync.** Track source `etag`/`modified` (T08) so you re-ingest only deltas.
- **Concurrency with backpressure.** Parse in a process pool (CPU-bound OCR); cap
  in-flight cloud-OCR calls with a semaphore to respect rate limits.
- **Observability.** Emit per-doc metrics: pages, chars, OCR-used, chunks, latency,
  failure reason. You *will* need these to debug "why isn't doc X searchable?"

```python
from concurrent.futures import ProcessPoolExecutor
def ingest_batch(paths, workers=8) -> list[IngestResult]:
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(ingest_one, paths))
```

---

## 7. Tables & images — don't lose them

- **Tables:** keep as a single chunk in Markdown/HTML form. Optionally generate a
  one-line LLM summary ("Table: Q3 revenue by region") and embed *that* for retrieval
  while returning the full table to the LLM (small-to-big, [T01 §2.5](01-rag-pipelines.md)).
- **Images/diagrams:** generate a text caption with a VLM and index the caption; store
  the image URI in metadata so the answer can link to it.
- **Charts:** VLMs can extract the underlying data points — far more useful to retrieve
  than "[image]".

---

## 8. Choosing your extractor

| Need | Use |
|------|-----|
| Fast born-digital PDF text | **PyMuPDF** |
| Clean Markdown + good tables, RAG-ready | **Docling** |
| Widest format coverage, element types | **Unstructured** |
| On-prem OCR, privacy | **Tesseract / RapidOCR** |
| Best table/form OCR, managed | **Azure DI / Textract / Google Doc AI** |
| Hardest layouts, charts, handwriting | **VLM (Claude vision)** |

Most teams run a **tiered** strategy: PyMuPDF/Docling for the 80% easy case, cloud DI or
VLM only for the documents that fail a quality check. This keeps cost down while covering
the long tail.

---

## 9. Checklist

- [ ] Detect type + scan-vs-digital before choosing an extractor.
- [ ] Preserve structure (headings/tables/reading order) for downstream chunking.
- [ ] OCR fallback triggered by low text yield, not file extension alone.
- [ ] Strip boilerplate; de-hyphenate; normalize Unicode.
- [ ] Quarantine failures; idempotent by content hash; incremental sync.
- [ ] Attach full metadata (source URI, page, tenant, ACL, updated_at) — see T01/T09.
- [ ] PII scan at ingest (T09) before anything is embedded.
- [ ] Emit per-document observability metrics.

**Next:** [03 — Vector Search Systems](03-vector-search.md) — indexing and querying the
chunks you just produced, at scale and low latency.
