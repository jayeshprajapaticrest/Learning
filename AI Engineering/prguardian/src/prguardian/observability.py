"""OBSERVABILITY.

Agentic systems are only trustworthy if you can see what they did. Two cheap,
high-value mechanisms:

* LangSmith tracing — set the env vars below and every LLM/graph step is traced
  with inputs, outputs, latency and token cost. No code changes needed; the
  langchain libraries emit traces automatically.
      LANGCHAIN_TRACING_V2=true
      LANGCHAIN_API_KEY=ls-...
      LANGCHAIN_PROJECT=pr-guardian

* A local structured run-log (below) so the pipeline is auditable even without
  LangSmith — useful for demos and for attaching evidence to a compliance trail.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


@dataclass
class RunLog:
    pr_id: str
    steps: list[dict] = field(default_factory=list)
    _t0: float = field(default_factory=time.monotonic)

    def step(self, name: str, **data) -> None:
        self.steps.append({
            "step": name,
            "t_ms": round((time.monotonic() - self._t0) * 1000),
            **data,
        })

    def as_json(self) -> str:
        return json.dumps({"pr_id": self.pr_id, "steps": self.steps}, indent=2)
