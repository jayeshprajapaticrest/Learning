"""LLM factory.

One place that knows how to build a Claude chat model. Every agent calls this
so the model configuration is consistent and swappable.
"""
from __future__ import annotations

from langchain_anthropic import ChatAnthropic

from . import config


def build_llm(model: str | None = None, *, temperature: float | None = None) -> ChatAnthropic:
    """Return a configured ChatAnthropic instance.

    Notes
    -----
    * Reads ANTHROPIC_API_KEY from the environment automatically.
    * `claude-opus-4-8` / `claude-sonnet-4-6` reject `temperature` *and* `top_p`
      together and reject `budget_tokens`. We leave sampling params unset by
      default. To enable extended thinking, pass thinking={"type": "adaptive"}
      (requires a langchain-anthropic build that forwards it) — never
      budget_tokens on 4.7+/Fable models.
    """
    kwargs: dict = {
        "model": model or config.SUPERVISOR_MODEL,
        "max_tokens": config.MAX_TOKENS,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ChatAnthropic(**kwargs)


def supervisor_llm() -> ChatAnthropic:
    """Most capable model — drives routing and final synthesis."""
    return build_llm(config.SUPERVISOR_MODEL)


def worker_llm() -> ChatAnthropic:
    """Cheaper/faster model — drives narrow worker sub-agents."""
    return build_llm(config.WORKER_MODEL)
