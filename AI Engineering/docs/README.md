# Enterprise RAG & Agentic AI Engineering — Tutorial Series

A hands-on, end-to-end curriculum for building production-grade Retrieval-Augmented
Generation (RAG) systems, LangGraph agents, and AI microservices for the enterprise.

These tutorials are written to be **practical and current** (2026). Every concept is
paired with runnable code, architecture diagrams (ASCII), and "production reality"
notes that explain what breaks at scale and how teams fix it.

---

## Who this is for

Engineers building LLM-powered systems that must be **accurate, secure, observable,
and multi-tenant** — not weekend demos. If you can write Python and understand HTTP
APIs, you can follow along.

## The stack we use

| Layer | Default choice | Alternatives covered |
|-------|----------------|----------------------|
| LLM | Claude (Opus 4.8 / Sonnet 4.6 / Haiku 4.5) | OpenAI, open-weights via vLLM |
| Orchestration | LangGraph | LlamaIndex, raw SDK |
| Vector DB | Qdrant | Weaviate, OpenSearch |
| Embeddings | `text-embedding-3-large`, `voyage-3`, `bge-m3` | Cohere, local SentenceTransformers |
| Reranker | Cohere Rerank 3 / `bge-reranker-v2-m3` | Voyage rerank, cross-encoders |
| API | FastAPI + Uvicorn | — |
| Cache | Redis | in-process LRU |
| Docs parsing | Unstructured, Docling, PyMuPDF, Azure Document Intelligence | Textract, Tesseract |

---

## Learning path

Read in order the first time; later use as reference.

| # | Tutorial | What you'll build |
|---|----------|-------------------|
| 01 | [RAG Pipelines](01-rag-pipelines.md) | Chunking → hybrid retrieval → reranking → query rewriting → generation |
| 02 | [Document Ingestion](02-document-ingestion.md) | A robust pipeline for PDF, DOCX, scanned images, and tables |
| 03 | [Vector Search Systems](03-vector-search.md) | Qdrant/Weaviate/OpenSearch indexes tuned for recall + latency |
| 04 | [LangGraph Agentic Workflows](04-langgraph-agents.md) | Tool-using agents with planning and self-healing |
| 05 | [Knowledge Layers & Ontology](05-knowledge-layers.md) | Multi-tenant, ontology-driven enterprise knowledge graph |
| 06 | [Guardrails, Hallucination Reduction & Evals](06-guardrails-evals.md) | Input/output guards + an automated eval harness |
| 07 | [FastAPI AI Microservices](07-fastapi-microservices.md) | Async, cached, streaming inference service |
| 08 | [Enterprise Integration & MCP](08-enterprise-integration.md) | Connectors for SharePoint, CRM, DBs, and MCP tools |
| 09 | [Security, PII & Governance](09-security-governance.md) | PII redaction, audit logs, access control, compliance |

### Part II — Deep Dives

For technique-level depth and complete framework feature references, continue to
**[Part II](part2-README.md)**:

| # | Tutorial | Focus |
|---|----------|-------|
| 10 | [RAG Engineering Deep Dive](10-rag-engineering.md) | Component-aware chunking · hybrid · rerank · Graph-RAG · multi-hop |
| 11 | [LangGraph — Complete Feature Reference](11-langgraph-features.md) | Every LangGraph primitive, single & multi-agent |
| 12 | [LangChain — Complete Feature Reference](12-langchain-features.md) | Every LangChain building block, single & multi-agent |
| 13 | [MCP Tools & Tool-Calling Workflows](13-mcp-tool-calling.md) | MCP + robust tool-calling loops |
| 14 | [Multi-Agent Orchestration](14-multi-agent-orchestration.md) | Supervisor · network · hierarchical · swarm · map-reduce |
| 15 | [Prompt Engineering & Hallucination Control](15-prompt-engineering-hallucination.md) | Techniques, structure, grounding |
| 16 | [Eval Frameworks & Synthetic Data](16-evals-synthetic-data.md) | Measuring RAG/agents + generating test/training data |

---

## The mental model

A production RAG/agent system is **five loops stacked on top of each other**:

```
                         ┌─────────────────────────────────────┐
                         │  GOVERNANCE LOOP (audit, evals, cost) │  ← T06, T09
                         │  ┌─────────────────────────────────┐ │
                         │  │  AGENT LOOP (plan→act→observe)    │ │  ← T04
                         │  │  ┌─────────────────────────────┐ │ │
                         │  │  │  RAG LOOP (retrieve→rerank→  │ │ │  ← T01, T03
                         │  │  │           →generate)         │ │ │
                         │  │  │  ┌───────────────────────┐  │ │ │
                         │  │  │  │ INGEST LOOP (parse→    │  │ │ │  ← T02
                         │  │  │  │   chunk→embed→index)   │  │ │ │
                         │  │  │  └───────────────────────┘  │ │ │
                         │  │  └─────────────────────────────┘ │ │
                         │  └─────────────────────────────────┘ │
                         └─────────────────────────────────────┘
                              all served via FastAPI  ← T07
                              all integrated with apps ← T08
```

If you remember one thing: **retrieval quality is the ceiling on answer quality.**
No prompt, model, or guardrail fixes documents the system never retrieved. Most of
your engineering effort should go into ingestion + retrieval, not prompt tweaking.

## How to use the code

Each tutorial's code is self-contained and assumes:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U \
  langchain langgraph langchain-anthropic langchain-openai \
  qdrant-client weaviate-client opensearch-py \
  unstructured[all-docs] docling pymupdf rapidocr-onnxruntime \
  fastapi uvicorn[standard] redis pydantic-settings \
  rank-bm25 cohere sentence-transformers \
  presidio-analyzer presidio-anonymizer ragas
```

Set keys via environment (never hardcode):

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...        # embeddings, optional
export COHERE_API_KEY=...        # reranking, optional
export QDRANT_URL=http://localhost:6333
```
