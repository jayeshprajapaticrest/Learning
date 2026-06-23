"""RAG ingestion — builds TWO vector collections:

* standards  — coding standards / review checklist (grounds the reviewers).
* incidents  — past postmortems (lets us flag "this change resembles INC-XYZ").

    python -m prguardian.ingest
"""
from __future__ import annotations

from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import config


def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)


def _store(collection: str) -> Chroma:
    return Chroma(
        collection_name=collection,
        embedding_function=get_embeddings(),
        persist_directory=str(config.VECTOR_DB_DIR),
    )


def standards_store() -> Chroma:
    return _store(config.STANDARDS_COLLECTION)


def incidents_store() -> Chroma:
    return _store(config.INCIDENTS_COLLECTION)


def _ingest_dir(directory, collection: str) -> int:
    loader = DirectoryLoader(
        str(directory), glob="**/*.md", loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    store = _store(collection)
    existing = store.get().get("ids", [])
    if existing:
        store.delete(ids=existing)
    store.add_documents(chunks)
    return len(chunks)


def ingest() -> dict[str, int]:
    return {
        "standards": _ingest_dir(config.STANDARDS_DIR, config.STANDARDS_COLLECTION),
        "incidents": _ingest_dir(config.INCIDENTS_DIR, config.INCIDENTS_COLLECTION),
    }


if __name__ == "__main__":
    counts = ingest()
    print(f"Ingested {counts} into Chroma at {config.VECTOR_DB_DIR}")
