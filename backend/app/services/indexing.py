"""Backfill embeddings for lessons and notes so semantic search / RAG work.

Idempotent: only rows missing an embedding are encoded. Cheap with the hashing
fallback; with sentence-transformers it runs once on first startup.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Lesson, Note
from . import embeddings

log = logging.getLogger("app.index")


async def backfill_embeddings(db: AsyncSession, batch: int = 64) -> dict:
    if not embeddings.available():
        return {"skipped": "no embedding provider"}
    counts: dict[str, int] = {}
    targets = (
        (Lesson, lambda r: f"{r.title}. {r.summary}"),
        (Note, lambda r: r.content),
    )
    for cls, text_fn in targets:
        rows = (await db.execute(select(cls).where(cls.embedding.is_(None)))).scalars().all()
        done = 0
        for i in range(0, len(rows), batch):
            chunk = rows[i : i + batch]
            vecs = await embeddings.embed([text_fn(r) for r in chunk])
            for r, v in zip(chunk, vecs):
                r.embedding = v
            await db.commit()
            done += len(chunk)
        counts[cls.__tablename__] = done
    if any(counts.values()):
        log.info("embeddings backfilled: %s (provider=%s)", counts, embeddings.provider())
    return counts
