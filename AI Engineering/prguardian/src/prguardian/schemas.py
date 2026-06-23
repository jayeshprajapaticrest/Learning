"""Typed contracts (guardrails).

Every LLM step that feeds a decision returns one of these Pydantic models via
`.with_structured_output(...)`. This is the difference between a demo and a
production agent: outputs are validated, not parsed out of free text.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low"]
Lens = Literal["security", "performance", "correctness", "style"]
Decision = Literal["auto_approve", "comment", "request_changes", "escalate"]


class Finding(BaseModel):
    """A single issue raised by a reviewer agent."""
    lens: Lens
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 self-assessed confidence")
    title: str
    detail: str
    file: Optional[str] = None
    suggestion: Optional[str] = None


class ReviewFindings(BaseModel):
    """A reviewer's full output for one lens."""
    findings: list[Finding] = Field(default_factory=list)


class Verdict(BaseModel):
    """The verifier's adversarial judgement of one finding."""
    index: int = Field(description="Index of the finding being judged")
    is_real: bool = Field(description="True only if the finding is a genuine, actionable issue")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class VerifyResult(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


class RiskRationale(BaseModel):
    """LLM-written explanation that accompanies the deterministic risk score."""
    summary: str
    release_note: str = Field(description="One-line release note for this PR")
