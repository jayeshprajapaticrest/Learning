"""CLI — run the gated PR review pipeline end to end.

    python -m prguardian.cli --pr PR-4521

The run pauses at the human approval gate (LangGraph interrupt); you approve or
reject at the terminal, and the graph resumes from exactly where it paused.
"""
from __future__ import annotations

import argparse
import asyncio

from langgraph.types import Command

from .graph import build_graph


async def run(pr_id: str) -> None:
    app = await build_graph(with_memory=True)
    config = {"configurable": {"thread_id": f"review-{pr_id}"}}

    print(f"▶ Reviewing {pr_id} ...\n")
    state = await app.ainvoke({"pr_id": pr_id}, config)

    # If the graph paused at the human gate, ask for a decision and resume.
    while "__interrupt__" in state:
        payload = state["__interrupt__"][0].value
        d = payload["decision"]
        print(f"\n⏸  HUMAN GATE — decision={d['decision']} risk={d['risk_score']}/100")
        print(payload.get("rationale", {}).get("summary", ""))
        for f in payload.get("findings", []):
            print(f"   • [{f['severity']}/{f['lens']}] {f['title']}")
        ans = input("\nApprove this action? [y/N] ").strip().lower()
        state = await app.ainvoke(
            Command(resume={"approved": ans == "y", "dismissed": []}),
            config,
        )

    print("\n" + "=" * 60)
    print(state.get("report", "(no report)"))


def main() -> None:
    parser = argparse.ArgumentParser(description="PR Guardian")
    parser.add_argument("--pr", default="PR-4521", help="PR id known to the MCP server")
    args = parser.parse_args()
    asyncio.run(run(args.pr))


if __name__ == "__main__":
    main()
