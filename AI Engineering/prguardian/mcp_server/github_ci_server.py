"""MCP server exposing GitHub + CI tools over stdio.

Simulated for the demo (canned PRs), but the tool *contract* is exactly what a
real GitHub/CI MCP server would expose — so the agent code never changes when
you point it at production. Discovered at runtime via langchain-mcp-adapters.

    python mcp_server/github_ci_server.py     # waits on stdio for an MCP client
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("devops")

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PR_DIR = ROOT / "data" / "sample_prs"

# Canned PR metadata. In production these come from the GitHub API.
_PRS = {
    "PR-4521": {"title": "Add user export endpoint", "diff_file": "pr_4521.diff", "ci": "passing"},
    "PR-4530": {"title": "Cache product catalog", "diff_file": "pr_4530.diff", "ci": "passing"},
}


@mcp.tool()
def get_pr_diff(pr_id: str) -> str:
    """Return the unified diff for a pull request."""
    pr = _PRS.get(pr_id.upper())
    if not pr:
        return f"Unknown PR {pr_id}."
    path = SAMPLE_PR_DIR / pr["diff_file"]
    return path.read_text(encoding="utf-8") if path.exists() else "(empty diff)"


@mcp.tool()
def get_pr_files(pr_id: str) -> str:
    """List the files changed in a pull request."""
    diff = get_pr_diff(pr_id)
    files = [ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/")]
    return "\n".join(files) if files else "(no files)"


@mcp.tool()
def get_ci_status(pr_id: str) -> str:
    """Return the CI status (passing/failing/pending) for a pull request."""
    pr = _PRS.get(pr_id.upper())
    return pr["ci"] if pr else "unknown"


@mcp.tool()
def post_review(pr_id: str, body: str) -> str:
    """Post a review comment on a pull request."""
    return f"Posted review on {pr_id} ({len(body)} chars)."


@mcp.tool()
def set_status(pr_id: str, state: str) -> str:
    """Set the review status of a pull request (e.g. request_changes, merged)."""
    return f"Set {pr_id} status -> {state}."


@mcp.tool()
def merge_pr(pr_id: str) -> str:
    """Merge a pull request."""
    return f"Merged {pr_id}."


if __name__ == "__main__":
    mcp.run(transport="stdio")
