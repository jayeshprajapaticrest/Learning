"""SINGLE-AGENT reviewer (ReAct) — the interactive counterpart to the pipeline.

The multi-agent graph is for automated, gated review. This single ReAct agent
is for a human who wants to *chat* about a PR: "why did you flag line 40?",
"check this against our auth standard". It can call the standards-search (RAG)
tool and the GitHub/CI MCP tools in a loop.
"""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from .llm import orchestrator_llm
from .memory import get_checkpointer
from .tools import LOCAL_TOOLS, load_mcp_tools

SYSTEM_PROMPT = (
    "You are PR Guardian, an expert code reviewer. Use standards_search to ground "
    "claims in the team's engineering standards, and the GitHub/CI tools to fetch "
    "the diff, files, and CI status. Be specific, cite standards, and never invent "
    "code that isn't in the diff."
)


async def build_interactive_reviewer(*, with_memory: bool = True):
    tools = list(LOCAL_TOOLS) + await load_mcp_tools()
    return create_react_agent(
        model=orchestrator_llm(),
        tools=tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=get_checkpointer() if with_memory else None,
    )
