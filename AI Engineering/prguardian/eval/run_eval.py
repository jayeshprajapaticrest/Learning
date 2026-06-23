"""EVALUATION harness.

You cannot ship an agent you can't measure. This runs the pipeline over a small
labeled set and checks two things per PR:

* decision quality — did the guardian land on an acceptable decision?
* recall — did it surface the expected issue (keyword match on findings)?

This is intentionally a STARTING POINT. In production you'd grow labeled_prs.jsonl,
add precision (false-positive rate), and wire this into CI / LangSmith datasets so
every prompt or model change is regression-tested before rollout.

    python eval/run_eval.py
"""
import asyncio
import json
from pathlib import Path

from langgraph.types import Command

from prguardian.graph import build_graph

DATA = Path(__file__).with_name("labeled_prs.jsonl")


async def evaluate() -> None:
    app = await build_graph(with_memory=False)
    cases = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]

    decision_hits = recall_hits = 0
    for case in cases:
        cfg = {"configurable": {"thread_id": f"eval-{case['pr_id']}"}}
        state = await app.ainvoke({"pr_id": case["pr_id"]}, cfg)
        while "__interrupt__" in state:  # auto-approve to reach the report
            state = await app.ainvoke(Command(resume={"approved": True, "dismissed": []}), cfg)

        decision = state["decision"]["decision"]
        report = state.get("report", "").lower()

        decision_ok = decision in case["expect_decision_in"]
        recall_ok = all(kw.lower() in report for kw in case["expect_keywords"])
        decision_hits += decision_ok
        recall_hits += recall_ok

        print(f"{case['pr_id']}: decision={decision} "
              f"[{'OK' if decision_ok else 'MISS'}]  recall=[{'OK' if recall_ok else 'MISS'}]")

    n = len(cases)
    print(f"\nDecision accuracy: {decision_hits}/{n}   Recall: {recall_hits}/{n}")


if __name__ == "__main__":
    asyncio.run(evaluate())
