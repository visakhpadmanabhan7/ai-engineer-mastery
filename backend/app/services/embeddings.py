"""Provider-agnostic text embeddings for semantic search / RAG.

Resolution order for `auto`:
  1. local  : sentence-transformers (best quality, free, optional dependency)
  2. openai : an OpenAI-compatible embeddings API (needs EMBEDDINGS_API_KEY)
  3. hash   : a dependency-free hashing embedding so search works out of the box

Every backend returns EMBED_DIM-length vectors so they fit the pgvector / JSON
column unchanged.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math

from ..config import settings
from ..models import EMBED_DIM

log = logging.getLogger("app.embed")

_st_model = None
_resolved: str | None = None


def _try_local() -> bool:
    global _st_model
    if _st_model is not None:
        return True
    try:
        from sentence_transformers import SentenceTransformer

        _st_model = SentenceTransformer(settings.embedding_model)
        log.info("embeddings: sentence-transformers (%s)", settings.embedding_model)
        return True
    except Exception as exc:
        log.info("sentence-transformers unavailable (%s)", exc)
        return False


def provider() -> str:
    global _resolved
    if _resolved:
        return _resolved
    p = settings.embeddings_provider.lower().strip()
    if p in ("local", "openai", "hash", "none"):
        _resolved = p
        return p
    # auto
    if _try_local():
        _resolved = "local"
    elif settings.embeddings_api_key.strip():
        _resolved = "openai"
    else:
        _resolved = "hash"
    log.info("embeddings provider (auto) -> %s", _resolved)
    return _resolved


def available() -> bool:
    return provider() != "none"


def _hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-hashed-tokens. Low quality (lexical), zero deps."""
    vec = [0.0] * EMBED_DIM
    for tok in (text or "").lower().split():
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % EMBED_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    p = provider()
    if p == "none":
        return [[0.0] * EMBED_DIM for _ in texts]
    if p == "local" and _try_local():
        vecs = await asyncio.to_thread(_st_model.encode, texts, normalize_embeddings=True)
        return [[float(x) for x in v] for v in vecs]
    if p == "openai":
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.embeddings_api_key, base_url=settings.embeddings_base_url)
            resp = await client.embeddings.create(
                model=settings.embeddings_api_model, input=texts, dimensions=EMBED_DIM
            )
            return [d.embedding for d in resp.data]
        except Exception as exc:
            log.warning("openai embeddings failed (%s); hashing fallback", exc)
    return [_hash_embed(t) for t in texts]


async def embed_one(text: str) -> list[float]:
    return (await embed([text]))[0]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
