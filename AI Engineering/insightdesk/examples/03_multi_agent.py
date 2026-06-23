"""Example 3 — Multi-agent supervisor team (RAG + MCP + calculator).

A single question that needs more than one specialist: the supervisor routes to
the researcher (knowledge base), the support worker (MCP ticket tools), and the
calculator, then synthesizes a final answer.

    python examples/03_multi_agent.py
"""
import asyncio

from langchain_core.messages import HumanMessage

from insightdesk.multi_agent import build_multi_agent


async def main() -> None:
    app = await build_multi_agent(with_memory=False)

    question = (
        "Look up ticket T-1001, tell me the SLA response target for a high "
        "priority ticket on the Pro plan, and how many hours that is times 2 "
        "(the escalation threshold)."
    )
    print(f"=== {question}\n")

    # Stream node-by-node so you can watch the supervisor route.
    async for event in app.astream({"messages": [HumanMessage(content=question)]}):
        for node, update in event.items():
            msgs = update.get("messages") if isinstance(update, dict) else None
            if msgs:
                print(f"[{node}] {msgs[-1].content[:300]}\n")
            elif isinstance(update, dict) and "next" in update:
                print(f"[supervisor -> {update['next']}]")


if __name__ == "__main__":
    asyncio.run(main())
