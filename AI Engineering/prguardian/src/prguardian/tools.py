"""TOOLS — local RAG tool + MCP tool loader.

The reviewers in the pipeline receive retrieved context directly (deterministic
fan-out). The standalone interactive reviewer (single_agent.py) uses these
tools in a ReAct loop instead.
"""
from __future__ import annotations

from langchain_core.tools import tool

from . import config
from .retriever import format_docs, search_standards


@tool
def standards_search(query: str) -> str:
    """Search the engineering standards / review checklist for relevant rules."""
    return format_docs(search_standards(query))


async def load_mcp_tools() -> list:
    """Load the GitHub/CI tools from the local MCP server (stdio subprocess).

    In production point this at your real GitHub/CI MCP server (HTTP/SSE) — the
    agent code is unchanged.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "devops": {
                "command": "python",
                "args": [config.MCP_SERVER_SCRIPT],
                "transport": "stdio",
            }
        }
    )
    return await client.get_tools()


LOCAL_TOOLS = [standards_search]
