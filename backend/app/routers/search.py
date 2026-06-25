"""Semantic search over the curriculum (pgvector-backed cosine when available,
lexical fallback otherwise)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import Lesson, User
from ..services import embeddings

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchIn(BaseModel):
    query: str
    k: int = Field(default=6, ge=1, le=20)


@router.post("")
async def search(data: SearchIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = (data.query or "").strip()
    if not q:
        return {"mode": "empty", "results": []}

    lessons = (await db.execute(select(Lesson))).scalars().all()
    embedded = [l for l in lessons if l.embedding]

    if embeddings.available() and embedded:
        qv = await embeddings.embed_one(q)
        scored = sorted(
            ((embeddings.cosine(qv, l.embedding), l) for l in embedded),
            key=lambda x: x[0], reverse=True,
        )[: data.k]
        return {
            "mode": "semantic", "provider": embeddings.provider(),
            "results": [
                {"day": l.day, "title": l.title, "summary": l.summary, "score": round(float(s), 4)}
                for s, l in scored
            ],
        }

    ql = q.lower()
    hits = [l for l in lessons if ql in (l.title or "").lower() or ql in (l.summary or "").lower()]
    return {
        "mode": "lexical",
        "results": [{"day": l.day, "title": l.title, "summary": l.summary} for l in hits[: data.k]],
    }
