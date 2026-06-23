"""Example 2 — RAG retrieval on its own (no agent).

Shows the vector-search layer directly: embed a query, return the nearest
knowledge-base chunks, and render them with their source paths. This is exactly
what the `knowledge_base_search` tool calls under the hood.

    python -m insightdesk.ingest      # build the vector store first
    python examples/02_rag.py
"""
from insightdesk.retriever import format_context, search


def main() -> None:
    query = "How are overage charges calculated?"
    print(f"Query: {query}\n")
    docs = search(query, k=3)
    print(format_context(docs))


if __name__ == "__main__":
    main()
