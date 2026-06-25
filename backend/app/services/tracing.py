"""Record one trace row per LLM call (tokens, estimated cost, latency, provider).
Best-effort and isolated: writes in its own session and never raises into the
request path."""
from __future__ import annotations

import logging

from ..config import settings
from ..database import SessionLocal
from ..models import LlmTrace

log = logging.getLogger("app.trace")

# Rough public list prices, USD per 1M tokens: (input, output).
PRICING = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
}


def est_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    cin, cout = PRICING.get(model, (0.0, 0.0))
    return round((prompt_tokens * cin + completion_tokens * cout) / 1_000_000, 6)


async def record(
    *, kind: str, provider: str = "", model: str = "",
    prompt_tokens: int = 0, completion_tokens: int = 0,
    latency_ms: int = 0, user_id: int | None = None, cache_hit: bool = False,
) -> None:
    if not settings.trace_enabled:
        return
    pt, ct = prompt_tokens or 0, completion_tokens or 0
    try:
        async with SessionLocal() as s:
            s.add(LlmTrace(
                kind=kind, provider=provider, model=model,
                prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct,
                est_cost_usd=est_cost(model, pt, ct), latency_ms=latency_ms,
                user_id=user_id, cache_hit=cache_hit,
            ))
            await s.commit()
    except Exception:  # pragma: no cover - never break a request over telemetry
        log.warning("trace record failed", exc_info=False)
