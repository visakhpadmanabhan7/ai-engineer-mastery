"""Small cache for LLM results: Redis when REDIS_URL is set, else an in-process
dict. Best-effort: any Redis error transparently falls back to memory. Callers
pass an already-hashed key."""
from __future__ import annotations

import json
import logging
import time

from ..config import settings

log = logging.getLogger("app.cache")

_redis = None
_redis_tried = False
_mem: dict[str, tuple[float, str]] = {}


def _client():
    global _redis, _redis_tried
    if _redis is None and not _redis_tried and settings.redis_url:
        _redis_tried = True
        try:
            import redis.asyncio as aioredis

            _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - depends on host
            log.warning("redis unavailable (%s); using in-process cache", exc)
            _redis = None
    return _redis


async def get(key: str):
    if not settings.cache_enabled:
        return None
    c = _client()
    if c is not None:
        try:
            v = await c.get(key)
            return json.loads(v) if v else None
        except Exception:  # pragma: no cover
            log.warning("cache get failed; memory fallback")
    item = _mem.get(key)
    if not item:
        return None
    exp, v = item
    if exp and exp < time.time():
        _mem.pop(key, None)
        return None
    return json.loads(v)


async def set(key: str, value, ttl: int | None = None) -> None:
    if not settings.cache_enabled:
        return
    ttl = settings.cache_ttl_seconds if ttl is None else ttl
    data = json.dumps(value)
    c = _client()
    if c is not None:
        try:
            await c.set(key, data, ex=ttl)
            return
        except Exception:  # pragma: no cover
            log.warning("cache set failed; memory fallback")
    _mem[key] = (time.time() + ttl if ttl else 0.0, data)


def backend() -> str:
    return "redis" if (settings.redis_url and _client() is not None) else "memory"
