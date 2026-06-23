"""Example 2 — Single ReAct reviewer (interactive style, one-shot here).

The agent fetches the diff via MCP, grounds itself with standards (RAG), and
answers a free-form question — the open-ended counterpart to the pipeline.

    python examples/02_single_reviewer.py
"""
import asyncio

from langchain_core.messages import HumanMessage

from prguardian.single_agent import build_interactive_reviewer


async def main() -> None:
    agent = await build_interactive_reviewer(with_memory=False)
    question = (
        "Fetch the diff for PR-4521 and tell me the single most serious problem, "
        "citing the exact engineering standard it violates."
    )
    result = await agent.ainvoke({"messages": [HumanMessage(content=question)]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
