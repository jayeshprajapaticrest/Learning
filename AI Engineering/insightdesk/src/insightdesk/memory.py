"""MEMORY & CONTEXT.

Two complementary layers, both first-class concepts in LangGraph:

1. Short-term (thread) memory — a *checkpointer*. LangGraph persists the full
   graph state after every step, keyed by a `thread_id`. Re-invoking the graph
   with the same thread_id replays the conversation, so the agent "remembers"
   earlier turns. We persist to SQLite so memory survives process restarts.

2. Long-term (cross-thread) memory — a *store*. A key/value space scoped by a
   namespace (e.g. per user) that any thread can read/write. We use it to
   remember durable facts about the user ("prefers Python", "on the Pro plan").
"""
from __future__ import annotations

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.memory import InMemoryStore

from . import config

# Long-term store is process-wide; a real deployment would back this with a
# database (e.g. langgraph's Postgres store).
_long_term_store = InMemoryStore()


def get_checkpointer() -> SqliteSaver:
    """Short-term memory: persists graph state per thread_id to SQLite."""
    # from_conn_string returns a context manager; we enter it and keep it open
    # for the lifetime of the process (fine for a CLI / demo).
    cm = SqliteSaver.from_conn_string(str(config.CHECKPOINT_DB))
    return cm.__enter__()


def get_store() -> InMemoryStore:
    """Long-term memory: cross-thread key/value store."""
    return _long_term_store


# --- Convenience helpers for the long-term store ---------------------------

def remember_fact(user_id: str, key: str, value: str) -> None:
    """Save a durable fact about a user."""
    _long_term_store.put(("users", user_id), key, {"value": value})


def recall_facts(user_id: str) -> dict[str, str]:
    """Return everything we know about a user."""
    items = _long_term_store.search(("users", user_id))
    return {item.key: item.value["value"] for item in items}
