"""Tiny in-memory, per-process rate limiter.

Caps AI-tutor calls per user so a public deployment running on the owner's API
key cannot be drained by anonymous sign-ups. In-memory and per-process, which is
fine for the single-instance free-tier deploy this app targets. For a multi-
instance deployment, front it with Redis (REDIS_URL is already wired in config).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


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
