"""Tiny in-memory, per-process rate limiter.

Caps AI-tutor calls per user so a public deployment running on the owner's API
key cannot be drained by anonymous sign-ups. In-memory and per-process, which is
fine for the single-instance free-tier deploy this app targets. For a multi-
instance deployment, front it with Redis (REDIS_URL is already wired in config).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

from ..config import settings

log = logging.getLogger("app.ratelimit")

_redis = None
_redis_tried = False


def _redis_client():
    global _redis, _redis_tried
    if _redis is None and not _redis_tried and settings.redis_url:
        _redis_tried = True
        try:
            import redis.asyncio as aioredis

            _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - depends on host
            log.warning("redis unavailable for rate limiting (%s); using in-process", exc)
            _redis = None
    return _redis


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float = 60.0) -> None:
        self.max_events = max_events
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record a hit for `key`; return False if it exceeds the window budget."""
        if self.max_events <= 0:  # 0 / negative => disabled (unlimited)
            return True
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_events:
                return False
            q.append(now)
            return True

    async def allow_async(self, key: str) -> bool:
        """Redis fixed-window when REDIS_URL is set (shared across instances),
        otherwise the in-process sliding window."""
        if self.max_events <= 0:
            return True
        c = _redis_client()
        if c is not None:
            try:
                rk = f"rl:{int(self.window)}:{key}"
                n = await c.incr(rk)
                if n == 1:
                    await c.expire(rk, int(self.window))
                return n <= self.max_events
            except Exception:  # pragma: no cover - fall back to memory
                pass
        return self.allow(key)
