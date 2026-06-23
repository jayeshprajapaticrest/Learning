"""PR Guardian — a self-improving, human-gated multi-agent code & release reviewer.

Covers single + multi-agent orchestration, RAG, vector search, MCP tools, and
short/long-term memory, plus the enterprise pieces that make agents trustworthy:
reflection/verification, deterministic risk scoring, human-in-the-loop approval,
self-improving feedback, observability, and an evaluation harness.

See README.md for the guided tour and PRESENTATION.md for the org deck.
"""
__all__ = ["config", "llm", "graph"]
