"""LLM factory — one place that builds Claude chat models."""
from __future__ import annotations

from langchain_anthropic import ChatAnthropic

from . import config


def build_llm(model: str | None = None) -> ChatAnthropic:
    """Configured ChatAnthropic. Reads ANTHROPIC_API_KEY from the environment.

    Sampling params and `budget_tokens` are intentionally unset — they error on
    Opus 4.8 / Sonnet 4.6. To enable extended thinking, pass
    thinking={"type": "adaptive"} (never budget_tokens on 4.7+/Fable models).
    """
    return ChatAnthropic(model=model or config.ORCHESTRATOR_MODEL, max_tokens=config.MAX_TOKENS)


def orchestrator_llm() -> ChatAnthropic:
    """Opus 4.8 — verification, risk rationale, report synthesis."""
    return build_llm(config.ORCHESTRATOR_MODEL)


def reviewer_llm() -> ChatAnthropic:
    """Sonnet 4.6 — fast/cheap parallel reviewers."""
    return build_llm(config.REVIEWER_MODEL)
