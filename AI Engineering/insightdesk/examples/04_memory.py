"""Example 4 — Memory & context.

Demonstrates both memory layers:

* Short-term (thread) memory via the checkpointer — the agent recalls an
  earlier turn in the same thread_id.
* Long-term (cross-thread) memory via the store — durable facts about a user.

    python examples/04_memory.py
"""
import asyncio

from langchain_core.messages import HumanMessage

from insightdesk.memory import recall_facts, remember_fact
from insightdesk.single_agent import build_single_agent


async def main() -> None:
    agent = await build_single_agent(with_mcp=False, with_memory=True)
    cfg = {"configurable": {"thread_id": "user-42-session-1"}}

    # --- Short-term memory: two turns in the same thread -------------------
    r1 = await agent.ainvoke(
        {"messages": [HumanMessage(content="My name is Jayesh and I'm on the Pro plan.")]},
        cfg,
    )
    print("Turn 1:", r1["messages"][-1].content, "\n")

    r2 = await agent.ainvoke(
        {"messages": [HumanMessage(content="What's my name and plan?")]},
        cfg,  # same thread_id -> the agent remembers turn 1
    )
    print("Turn 2:", r2["messages"][-1].content, "\n")

    # --- Long-term memory: durable cross-thread facts ----------------------
    remember_fact("user-42", "preferred_language", "Python")
    remember_fact("user-42", "plan", "Pro")
    print("Long-term facts for user-42:", recall_facts("user-42"))


if __name__ == "__main__":
    asyncio.run(main())
