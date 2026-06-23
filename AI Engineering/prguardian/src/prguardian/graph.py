"""The PR Guardian orchestration graph (the multi-agent system).

Pipeline (a LangGraph StateGraph):

    intake ─▶ retrieve ─▶ ┌ review_security ┐
                          ├ review_performance ┤
                          ├ review_correctness ┤─▶ verify ─▶ risk ─▶ human_gate ─▶ act ─▶ learn ─▶ report
                          └ review_style       ┘   (reflection)  (deterministic)  (interrupt)  (MCP)  (memory)

* reviewers run in PARALLEL (fan-out), results merged via an `operator.add` reducer.
* `verify` is the reflection step; `risk` is deterministic; `human_gate` pauses
  the graph with `interrupt()`; `act` calls GitHub/CI via MCP; `learn` writes
  the self-improving feedback.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import risk
from .llm import orchestrator_llm
from .memory import get_checkpointer, record_feedback
from .reviewers import LENSES
from .reviewers import run_reviewer
from .retriever import search_incidents
from .schemas import Finding, RiskRationale
from .tools import load_mcp_tools
from .verify import verify_findings


class ReviewState(TypedDict, total=False):
    pr_id: str
    diff: str
    ci_status: str
    similar_incidents: list[dict]
    findings: Annotated[list[Finding], operator.add]   # merged across reviewers
    verified: list[Finding]
    decision: dict
    rationale: dict
    approved: bool
    dismissed: list[str]
    report: str


def _tool_map(tools: list) -> dict:
    return {t.name: t for t in tools}


async def build_graph(*, with_memory: bool = True):
    mcp = _tool_map(await load_mcp_tools())

    # --- nodes --------------------------------------------------------------
    async def intake(state: ReviewState) -> dict:
        pr_id = state["pr_id"]
        diff = await mcp["get_pr_diff"].ainvoke({"pr_id": pr_id})
        ci = await mcp["get_ci_status"].ainvoke({"pr_id": pr_id})
        return {"diff": diff, "ci_status": ci, "findings": []}

    async def retrieve(state: ReviewState) -> dict:
        # Similarity search: does this change resemble a past incident?
        hits = search_incidents(state["diff"][:1500], k=2)
        similar = [
            {"source": d.metadata.get("source", "?"), "score": round(s, 3)}
            for d, s in hits if s >= 0.3
        ]
        return {"similar_incidents": similar}

    def make_reviewer(lens: str):
        async def node(state: ReviewState) -> dict:
            result = await run_reviewer(lens, state["diff"])
            return {"findings": result.findings}
        node.__name__ = f"review_{lens}"
        return node

    async def verify(state: ReviewState) -> dict:
        kept = await verify_findings(state["diff"], state.get("findings", []))
        return {"verified": kept}

    async def risk_node(state: ReviewState) -> dict:
        verified = state.get("verified", [])
        decision = risk.decide(verified)
        # LLM writes only the explanation — the decision itself is deterministic.
        listing = "\n".join(f"- [{f.severity}] {f.title}" for f in verified) or "No issues."
        llm = orchestrator_llm().with_structured_output(RiskRationale)
        rat: RiskRationale = await llm.ainvoke(
            f"Decision: {decision['decision']} (risk {decision['risk_score']}/100). "
            f"CI: {state.get('ci_status')}. Verified findings:\n{listing}\n\n"
            "Write a 2-3 sentence reviewer summary and a one-line release note."
        )
        return {"decision": decision, "rationale": rat.model_dump()}

    def human_gate(state: ReviewState) -> dict:
        decision = state["decision"]
        if not decision.get("requires_approval"):
            return {"approved": True, "dismissed": []}
        # Pause the graph. Resume with Command(resume={"approved": bool, "dismissed": [...]})
        human = interrupt({
            "pr_id": state["pr_id"],
            "decision": decision,
            "rationale": state.get("rationale"),
            "findings": [f.model_dump() for f in state.get("verified", [])],
        })
        return {"approved": bool(human.get("approved", False)),
                "dismissed": human.get("dismissed", [])}

    async def act(state: ReviewState) -> dict:
        pr_id, decision = state["pr_id"], state["decision"]
        body = state.get("rationale", {}).get("summary", "Automated review.")
        await mcp["post_review"].ainvoke({"pr_id": pr_id, "body": body})
        if state.get("approved") and decision["decision"] == "auto_approve":
            await mcp["merge_pr"].ainvoke({"pr_id": pr_id})
            await mcp["set_status"].ainvoke({"pr_id": pr_id, "state": "merged"})
        else:
            await mcp["set_status"].ainvoke({"pr_id": pr_id, "state": decision["decision"]})
        return {}

    def learn(state: ReviewState) -> dict:
        # Self-improving: dismissed findings teach the reviewers to be quieter.
        dismissed = set(state.get("dismissed", []))
        for f in state.get("verified", []):
            record_feedback(f.lens, f.title, accepted=f.title not in dismissed)
        return {}

    async def report(state: ReviewState) -> dict:
        d = state["decision"]
        rat = state.get("rationale", {})
        lines = [
            f"# PR Guardian review — {state['pr_id']}",
            f"**Decision:** {d['decision']}  |  **Risk:** {d['risk_score']}/100  |  "
            f"**CI:** {state.get('ci_status')}",
            "",
            rat.get("summary", ""),
        ]
        if state.get("similar_incidents"):
            inc = ", ".join(f"{i['source']} ({i['score']})" for i in state["similar_incidents"])
            lines += ["", f"⚠️ Resembles past incident(s): {inc}"]
        if state.get("verified"):
            lines += ["", "## Findings"]
            for f in state["verified"]:
                lines.append(f"- **[{f.severity}/{f.lens}]** {f.title} — {f.detail}"
                             + (f"\n  - _suggestion:_ {f.suggestion}" if f.suggestion else ""))
        else:
            lines += ["", "No blocking findings. ✅"]
        lines += ["", f"_Release note:_ {rat.get('release_note', '')}"]
        return {"report": "\n".join(lines)}

    # --- wiring -------------------------------------------------------------
    g = StateGraph(ReviewState)
    g.add_node("intake", intake)
    g.add_node("retrieve", retrieve)
    for lens in LENSES:
        g.add_node(f"review_{lens}", make_reviewer(lens))
    g.add_node("verify", verify)
    g.add_node("risk", risk_node)
    g.add_node("human_gate", human_gate)
    g.add_node("act", act)
    g.add_node("learn", learn)
    g.add_node("report", report)

    g.add_edge(START, "intake")
    g.add_edge("intake", "retrieve")
    for lens in LENSES:                       # fan-out (parallel)
        g.add_edge("retrieve", f"review_{lens}")
        g.add_edge(f"review_{lens}", "verify")  # fan-in barrier
    g.add_edge("verify", "risk")
    g.add_edge("risk", "human_gate")
    g.add_edge("human_gate", "act")
    g.add_edge("act", "learn")
    g.add_edge("learn", "report")
    g.add_edge("report", END)

    checkpointer = get_checkpointer() if with_memory else None
    return g.compile(checkpointer=checkpointer)
