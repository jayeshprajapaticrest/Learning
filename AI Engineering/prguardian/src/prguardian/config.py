"""Central configuration for PR Guardian."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
STANDARDS_DIR = ROOT / "data" / "standards"
INCIDENTS_DIR = ROOT / "data" / "past_incidents"
SAMPLE_PR_DIR = ROOT / "data" / "sample_prs"
VECTOR_DB_DIR = ROOT / ".chroma"
CHECKPOINT_DB = ROOT / ".checkpoints.sqlite"

# --- Models ----------------------------------------------------------------
# Opus 4.8 for the decisions that must be right (verify, risk rationale,
# report). Sonnet 4.6 for the parallel reviewer fan-out (fast + cheap).
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "claude-opus-4-8")
REVIEWER_MODEL = os.getenv("REVIEWER_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))

# --- Embeddings (local, no key) --------------------------------------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# --- RAG -------------------------------------------------------------------
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
RETRIEVAL_K = 4
STANDARDS_COLLECTION = "prg_standards"
INCIDENTS_COLLECTION = "prg_incidents"

# --- Risk policy (deterministic, auditable) --------------------------------
SEVERITY_WEIGHTS = {"critical": 40, "high": 20, "medium": 8, "low": 2}
# Verified findings below this confidence are dropped.
MIN_CONFIDENCE = 0.55
# Risk score thresholds -> decision.
RISK_BLOCK = 40          # >= this => request_changes / escalate
RISK_COMMENT = 10        # >= this => comment, < this => auto-approve

# --- MCP -------------------------------------------------------------------
MCP_SERVER_SCRIPT = str(ROOT / "mcp_server" / "github_ci_server.py")
