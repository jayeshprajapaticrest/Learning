"""Example 4 — Human-in-the-loop + self-improving memory.

Shows the two enterprise-defining behaviours:

1. The graph PAUSES at the approval gate (LangGraph `interrupt`). State is
   checkpointed; we inspect the decision, then resume with a human verdict.
2. When we dismiss a finding, `learn` records it. Re-running the same review
   later, that lens is biased to stay quieter — the system improves from
   feedback.

    python examples/04_human_in_the_loop.py
"""
import asyncio

from langgraph.types import Command

from prguardian.graph import build_graph
from prguardian.memory import feedback_hint


async def main() -> None:
    app = await build_graph(with_memory=True)
    cfg = {"configurable": {"thread_id": "hitl-PR-4521"}}

    state = await app.ainvoke({"pr_id": "PR-4521"}, cfg)

    if "__interrupt__" in state:
        payload = state["__interrupt__"][0].value
        print(f"⏸  PAUSED at gate — decision={payload['decision']['decision']} "
              f"risk={payload['decision']['risk_score']}/100")
        titles = [f["title"] for f in payload["findings"]]
        print("   findings:", titles)

        # Human verdict: reject the merge, and dismiss the first finding as noise.
        dismissed = titles[:1]
        state = await app.ainvoke(
            Command(resume={"approved": False, "dismissed": dismissed}), cfg
        )
        print(f"\n▶ Resumed. Dismissed (teaches the reviewers): {dismissed}")

    print("\nLearned hint now injected into future 'security' reviews:")
    print(" ", feedback_hint("security") or "(none yet)")


if __name__ == "__main__":
    asyncio.run(main())
