"""RISK SCORING & DECISION POLICY.

Deliberately DETERMINISTIC. The decision an engineer's merge depends on must be
auditable and reproducible — so the score is computed from verified findings by
a fixed formula, not asked of an LLM. The LLM only writes the human-readable
rationale and release note (see graph.py). This split — deterministic decision,
LLM explanation — is a core enterprise-readiness talking point.
"""
from __future__ import annotations

from . import config
from .schemas import Finding


def score(findings: list[Finding]) -> int:
    """Weighted, confidence-scaled risk score (0-100)."""
    total = 0.0
    for f in findings:
        total += config.SEVERITY_WEIGHTS.get(f.severity, 0) * f.confidence
    return min(100, round(total))


def decide(findings: list[Finding]) -> dict:
    s = score(findings)
    has_critical = any(f.severity == "critical" for f in findings)

    if has_critical or s >= config.RISK_BLOCK:
        decision = "escalate" if has_critical else "request_changes"
    elif s >= config.RISK_COMMENT:
        decision = "comment"
    else:
        decision = "auto_approve"

    # Anything that changes merge state needs a human sign-off.
    requires_approval = decision in {"request_changes", "escalate", "auto_approve"}
    return {
        "risk_score": s,
        "decision": decision,
        "requires_approval": requires_approval,
        "counts": {
            sev: sum(1 for f in findings if f.severity == sev)
            for sev in ("critical", "high", "medium", "low")
        },
    }
