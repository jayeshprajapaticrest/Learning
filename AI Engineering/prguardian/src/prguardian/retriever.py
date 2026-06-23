"""RAG retrieval — semantic search over standards and past incidents."""
from __future__ import annotations

from langchain_core.documents import Document

from . import config
from .ingest import incidents_store, standards_store


def search_standards(query: str, k: int | None = None) -> list[Document]:
    return standards_store().similarity_search(query, k=k or config.RETRIEVAL_K)


def search_incidents(query: str, k: int = 3) -> list[tuple[Document, float]]:
    """Return (doc, similarity_score) so we can decide whether a match is close
    enough to warn about ('this change resembles a past incident')."""
    return incidents_store().similarity_search_with_relevance_scores(query, k=k)


def format_docs(docs: list[Document]) -> str:
    if not docs:
        return "No relevant standards found."
    return "\n\n".join(
        f"[{i}] (source: {d.metadata.get('source', '?')})\n{d.page_content.strip()}"
        for i, d in enumerate(docs, 1)
    )
