"""MEMORY — two layers, both native to LangGraph.

1. Short-term (checkpointer, SQLite): persists the review graph's state per
   thread_id. This is what powers human-in-the-loop: when the graph hits an
   approval `interrupt`, its state is checkpointed; resuming continues exactly
   where it paused — even after a process restart.

2. Long-term (store): the SELF-IMPROVING layer. After each review we record
   which findings a human accepted vs dismissed, keyed by lens + signature.
   Future reviews read this back to bias toward findings the team values and
   suppress patterns the team repeatedly dismisses.
"""
from __future__ import annotations

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.memory import InMemoryStore

from . import config

_store = InMemoryStore()


def get_checkpointer() -> SqliteSaver:
    cm = SqliteSaver.from_conn_string(str(config.CHECKPOINT_DB))
    return cm.__enter__()


def get_store() -> InMemoryStore:
    return _store


# --- Self-improving feedback API -------------------------------------------

def record_feedback(lens: str, finding_title: str, accepted: bool) -> None:
    """Record whether a human accepted a finding. Aggregates per (lens, title)."""
    ns = ("feedback", lens)
    key = finding_title.lower().strip()[:120]
    item = _store.get(ns, key)
    stats = item.value if item else {"accepted": 0, "dismissed": 0}
    stats["accepted" if accepted else "dismissed"] += 1
    _store.put(ns, key, stats)


def feedback_hint(lens: str) -> str:
    """Build a short hint from accumulated feedback to inject into a reviewer's
    prompt — the mechanism by which the system gets better over time."""
    items = _store.search(("feedback", lens))
    dismissed = [i.key for i in items if i.value.get("dismissed", 0) > i.value.get("accepted", 0)]
    if not dismissed:
        return ""
    joined = "; ".join(dismissed[:5])
    return (
        "\nLearned from past reviews — the team has repeatedly DISMISSED findings "
        f"like these, so only raise them with strong evidence: {joined}."
    )
