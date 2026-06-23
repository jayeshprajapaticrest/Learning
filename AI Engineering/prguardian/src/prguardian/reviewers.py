"""The specialist REVIEWER agents (the multi-agent fan-out).

Each reviewer owns one lens (security / performance / correctness / style),
sees the diff + lens-specific retrieved standards + the team's learned
feedback, and returns validated `Finding`s via structured output.

Design choice worth defending in a review: for a *bounded* task like this,
constrained structured output is more reliable and cheaper than a free-form
ReAct loop. We keep the ReAct pattern for the open-ended interactive reviewer
(single_agent.py).
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from .llm import reviewer_llm
from .memory import feedback_hint
from .retriever import format_docs, search_standards
from .schemas import ReviewFindings

LENSES: dict[str, str] = {
    "security": (
        "You are a security reviewer. Hunt for injection, secrets in code, "
        "auth/authorization gaps, unsafe deserialization, SSRF, and dependency risks."
    ),
    "performance": (
        "You are a performance reviewer. Hunt for N+1 queries, unbounded loops, "
        "blocking I/O on hot paths, missing pagination/limits, and memory blowups."
    ),
    "correctness": (
        "You are a correctness reviewer. Hunt for logic bugs, unhandled errors, "
        "race conditions, missing/weak tests, and breaking API changes."
    ),
    "style": (
        "You are a style & docs reviewer. Flag unclear naming, missing docs on "
        "public APIs, and deviations from the team checklist. Keep severity low "
        "unless it harms maintainability."
    ),
}


async def run_reviewer(lens: str, diff: str) -> ReviewFindings:
    """Run one lens reviewer over a diff and return validated findings."""
    standards = format_docs(search_standards(f"{lens} review rules", k=3))
    hint = feedback_hint(lens)

    system = SystemMessage(content=(
        f"{LENSES[lens]}\n\n"
        "Use the engineering standards below as ground truth. Report only "
        "genuine, actionable issues — no nitpicks dressed up as risks. Set "
        "`confidence` honestly and `severity` proportionate to real impact."
        f"{hint}\n\n--- ENGINEERING STANDARDS ---\n{standards}"
    ))
    user = HumanMessage(content=f"Review this unified diff for {lens} issues:\n\n```diff\n{diff}\n```")

    llm = reviewer_llm().with_structured_output(ReviewFindings)
    result: ReviewFindings = await llm.ainvoke([system, user])
    # Stamp the lens in case the model omits it.
    for f in result.findings:
        f.lens = lens  # type: ignore[assignment]
    return result
