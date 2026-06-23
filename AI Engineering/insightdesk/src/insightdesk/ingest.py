"""RAG — Step 1: INGESTION (vector storing).

Loads the markdown knowledge base, splits it into overlapping chunks, embeds
each chunk, and persists the vectors in a local Chroma collection.

Run once (and re-run whenever the docs change):

    python -m insightdesk.ingest
"""
from __future__ import annotations

from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import config


def get_embeddings() -> HuggingFaceEmbeddings:
    """Local sentence-transformer embeddings — no API key required."""
    return HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)


def get_vectorstore() -> Chroma:
    """Open (or create) the persisted Chroma collection."""
    return Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(config.VECTOR_DB_DIR),
    )


def ingest() -> int:
    """Load -> split -> embed -> store. Returns the number of chunks written."""
    # 1. LOAD raw documents from the knowledge base directory.
    loader = DirectoryLoader(
        str(config.KNOWLEDGE_BASE_DIR),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()

    # 2. SPLIT into overlapping chunks so retrieval returns focused context.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)

    # 3. EMBED + STORE. Chroma computes embeddings via the embedding_function
    #    and persists vectors + metadata to disk.
    store = get_vectorstore()
    # Rebuild cleanly so re-running ingest never duplicates chunks.
    existing = store.get().get("ids", [])
    if existing:
        store.delete(ids=existing)
    store.add_documents(chunks)

    return len(chunks)


if __name__ == "__main__":
    n = ingest()
    print(f"Ingested {n} chunks into Chroma at {config.VECTOR_DB_DIR}")
