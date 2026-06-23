"""Central configuration.

Everything tunable lives here so the rest of the codebase reads cleanly.
Model IDs follow the current Anthropic catalog — use the exact strings, never
append date suffixes.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env once, at import time.
load_dotenv()

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]          # .../insightdesk
KNOWLEDGE_BASE_DIR = ROOT / "data" / "knowledge_base"
VECTOR_DB_DIR = ROOT / ".chroma"                     # persisted Chroma store
CHECKPOINT_DB = ROOT / ".checkpoints.sqlite"         # LangGraph short-term memory

# --- Models (Anthropic via langchain-anthropic) ----------------------------
# Opus 4.8 is the most capable model — used for the supervisor and reasoning.
# Sonnet 4.6 is faster/cheaper — used for narrow worker sub-agents.
SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", "claude-opus-4-8")
WORKER_MODEL = os.getenv("WORKER_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))

# --- Embeddings (local, no API key needed) ---------------------------------
# A small, fast sentence-transformer. Swap for any embedding model you like.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# --- RAG knobs -------------------------------------------------------------
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
RETRIEVAL_K = 4                                      # top-k chunks per query
COLLECTION_NAME = "insightdesk_kb"

# --- MCP -------------------------------------------------------------------
# Path to the local MCP server we ship in mcp_server/server.py.
MCP_SERVER_SCRIPT = str(ROOT / "mcp_server" / "server.py")
