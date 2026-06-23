"""REFLECTION / VERIFICATION loop.

Reviewers over-report. A separate verifier (the stronger Opus model) acts as an
adversarial skeptic: for each finding it decides whether the issue is *real and
actionable*. Findings judged not-real, or below the confidence floor, are
dropped before they ever reach a human. This is the single biggest lever on
trust — it's how you keep false-positive rate low enough that engineers don't
start ignoring the bot.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from . import config
from .llm import orchestrator_llm
from .schemas import Finding, VerifyResult


async def verify_findings(diff: str, findings: list[Finding]) -> list[Finding]:
    if not findings:
        return []

    listing = "\n".join(
        f"{i}. [{f.lens}/{f.severity}] {f.title} — {f.detail}"
        for i, f in enumerate(findings)
    )
    system = SystemMessage(content=(
        "You are an adversarial verifier. For each candidate finding, decide if "
        "it is a GENUINE, actionable issue actually supported by the diff. "
        "Default to is_real=false when the evidence is weak, speculative, or the "
        "code in question is not present in the diff. Be strict — your job is to "
        "protect engineers from noise."
    ))
    user = HumanMessage(content=(
        f"DIFF:\n```diff\n{diff}\n```\n\nCANDIDATE FINDINGS:\n{listing}\n\n"
        "Return a verdict for every finding by index."
    ))

    llm = orchestrator_llm().with_structured_output(VerifyResult)
    result: VerifyResult = await llm.ainvoke([system, user])

    verdict_by_index = {v.index: v for v in result.verdicts}
    kept: list[Finding] = []
    for i, f in enumerate(findings):
        v = verdict_by_index.get(i)
        if v and v.is_real and v.confidence >= config.MIN_CONFIDENCE:
            # Trust the verifier's confidence over the reviewer's.
            f.confidence = v.confidence
            kept.append(f)
    return kept
