"""SINGLE-AGENT implementation (ReAct).

The simplest useful agent: one LLM in a loop that can call tools until it has
enough information to answer. LangGraph's `create_react_agent` builds this
graph for us (LLM node <-> tool node, looping on tool calls).

This single agent already demonstrates RAG (via the knowledge_base_search
tool), tools, and — when given a checkpointer — short-term memory.
"""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from .llm import supervisor_llm
from .memory import get_checkpointer
from .tools import LOCAL_TOOLS, load_mcp_tools

SYSTEM_PROMPT = (
    "You are InsightDesk, a precise support & research assistant. "
    "Prefer the knowledge_base_search tool for product/policy questions and "
    "cite the source paths it returns. Use calculate for arithmetic. "
    "If a question is outside the knowledge base, say so plainly."
)


async def build_single_agent(*, with_mcp: bool = True, with_memory: bool = True):
    """Construct a ReAct agent.

    Parameters
    ----------
    with_mcp:    also load tools from the MCP server.
    with_memory: attach the SQLite checkpointer for short-term (thread) memory.
    """
    tools = list(LOCAL_TOOLS)
    if with_mcp:
        tools += await load_mcp_tools()

    checkpointer = get_checkpointer() if with_memory else None

    return create_react_agent(
        model=supervisor_llm(),
        tools=tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
