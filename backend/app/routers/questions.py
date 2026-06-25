"""The full interview question bank, grouped by topic (for the browse view)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import Question, User

router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.get("")
async def all_questions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Question).order_by(Question.topic, Question.id))).scalars().all()
    by_topic: dict[str, list] = {}
    for q in rows:
        by_topic.setdefault(q.topic or "general", []).append(
            {"id": q.id, "prompt": q.prompt, "answer_key": q.answer_key, "difficulty": q.difficulty}
        )
    return {
        "total": len(rows),
        "topics": [
            {"topic": t, "count": len(qs), "questions": qs} for t, qs in by_topic.items()
        ],
    }
