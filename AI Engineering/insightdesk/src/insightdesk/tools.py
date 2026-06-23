"""TOOLS the agents can call.

Three flavours, to show the full range:

* `knowledge_base_search` — a local Python tool that performs RAG retrieval.
* `calculate` — a trivial local tool (deterministic, no LLM needed).
* `load_mcp_tools()` — tools discovered at runtime from an MCP server using
  langchain-mcp-adapters. This is how you plug in standardized, external
  capabilities (here: a tiny "support ticket" server we ship locally).
"""
from __future__ import annotations

from langchain_core.tools import tool

from . import config
from .retriever import format_context, search


@tool
def knowledge_base_search(query: str) -> str:
    """Search InsightDesk's internal knowledge base (product docs, billing,
    policies) and return the most relevant passages. Use this for any question
    about the product, plans, limits, or company policy."""
    docs = search(query)
    return format_context(docs)


@tool
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression, e.g. '1280 * 0.2'. Supports
    + - * / ** and parentheses only."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "Error: only numbers and + - * / ( ) are allowed."
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307 - sandboxed chars
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


async def load_mcp_tools() -> list:
    """Connect to the local MCP server and return its tools as LangChain tools.

    The MCP server is launched as a subprocess over stdio. In production this
    could just as easily be a remote HTTP/SSE MCP server.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "support": {
                "command": "python",
                "args": [config.MCP_SERVER_SCRIPT],
                "transport": "stdio",
            }
        }
    )
    return await client.get_tools()


# Tools that need no async setup — safe to import directly.
LOCAL_TOOLS = [knowledge_base_search, calculate]
