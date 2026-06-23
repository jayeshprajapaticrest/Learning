"""Example 3 — Full multi-agent pipeline (auto-approving the gate).

Runs intake -> RAG -> parallel reviewers -> verify -> risk -> human gate ->
act -> learn -> report. Here we auto-approve at the gate so it runs unattended;
see example 04 for the interactive human-in-the-loop version.

    python examples/03_full_pipeline.py
"""
import asyncio

from langgraph.types import Command

from prguardian.graph import build_graph


async def main() -> None:
    app = await build_graph(with_memory=True)
    cfg = {"configurable": {"thread_id": "demo-PR-4521"}}

    state = await app.ainvoke({"pr_id": "PR-4521"}, cfg)
    # Auto-approve if the graph paused at the human gate.
    while "__interrupt__" in state:
        print(f"[gate] auto-approving: {state['__interrupt__'][0].value['decision']}")
        state = await app.ainvoke(Command(resume={"approved": True, "dismissed": []}), cfg)

    print("\n" + state["report"])


if __name__ == "__main__":
    asyncio.run(main())
