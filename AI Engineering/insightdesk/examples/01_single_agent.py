"""Example 1 — Single ReAct agent (RAG + local tools).

The agent decides on its own to call `knowledge_base_search` (RAG) or
`calculate`, then answers. No multi-agent routing, no MCP — the smallest
end-to-end loop.

    python examples/01_single_agent.py
"""
import asyncio

from langchain_core.messages import HumanMessage

from insightdesk.single_agent import build_single_agent


async def main() -> None:
    agent = await build_single_agent(with_mcp=False, with_memory=False)

    for question in [
        "What does the Pro plan cost and what is the overage rate?",
        "If I send 6000 messages on Pro, what's my overage charge?",
    ]:
        print(f"\n=== {question}")
        result = await agent.ainvoke({"messages": [HumanMessage(content=question)]})
        print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
