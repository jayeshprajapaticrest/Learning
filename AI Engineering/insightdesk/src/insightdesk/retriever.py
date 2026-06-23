"""RAG — Step 2: RETRIEVAL (vector searching).

Thin helpers over the persisted Chroma store. Given a natural-language query,
embed it and return the most similar knowledge-base chunks.
"""
from __future__ import annotations

from langchain_core.documents import Document

from . import config
from .ingest import get_vectorstore


def search(query: str, k: int | None = None) -> list[Document]:
    """Semantic search: embed the query, return the top-k nearest chunks."""
    store = get_vectorstore()
    return store.similarity_search(query, k=k or config.RETRIEVAL_K)


def format_context(docs: list[Document]) -> str:
    """Render retrieved chunks into a citation-friendly string for the LLM."""
    if not docs:
        return "No relevant documents found in the knowledge base."
    blocks = []
    for i, d in enumerate(docs, 1):
        source = d.metadata.get("source", "unknown")
        blocks.append(f"[{i}] (source: {source})\n{d.page_content.strip()}")
    return "\n\n".join(blocks)
