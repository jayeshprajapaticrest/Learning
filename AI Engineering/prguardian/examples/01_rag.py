"""Example 1 — RAG: standards grounding + incident similarity (no LLM).

    python -m prguardian.ingest      # build the vector store first
    python examples/01_rag.py
"""
from prguardian.retriever import format_docs, search_incidents, search_standards


def main() -> None:
    print("== Standards relevant to 'sql injection export endpoint' ==")
    print(format_docs(search_standards("sql injection export endpoint", k=2)))

    print("\n== Past incidents similar to a new export endpoint ==")
    query = "new endpoint exports user data, builds SQL with f-string, no auth check"
    for doc, score in search_incidents(query, k=2):
        print(f"  {doc.metadata.get('source')}  (similarity {score:.3f})")


if __name__ == "__main__":
    main()
