from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import Question, ReviewCard, ReviewLog, User
from ..schemas import ReviewGradeIn, ReviewStats
from ..services import srs
from ..services.activity import touch_streak

router = APIRouter(prefix="/api/review", tags=["review"])

NEW_PER_DAY = 15


def _q(q: Question, due, state, reps) -> dict:
    return {
        "question": {
            "id": q.id, "topic": q.topic, "prompt": q.prompt,
            "answer_key": q.answer_key, "difficulty": q.difficulty,
        },
        "due": due, "state": state, "reps": reps,
    }


@router.get("/queue")
async def queue(limit: int = 20, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    items: list[dict] = []

    # 1) due cards
    due = (await db.execute(
        select(ReviewCard, Question)
        .join(Question, Question.id == ReviewCard.question_id)
        .where(ReviewCard.user_id == user.id, ReviewCard.due <= now)
        .order_by(ReviewCard.due)
        .limit(limit)
    )).all()
    for card, q in due:
        items.append(_q(q, card.due, card.state, card.reps))

    # 2) backfill with brand-new questions (no card yet)
    if len(items) < limit:
        seen = (await db.execute(
            select(ReviewCard.question_id).where(ReviewCard.user_id == user.id)
        )).scalars().all()
        new_qs = (await db.execute(
            select(Question).where(~Question.id.in_(seen)).order_by(Question.id).limit(min(NEW_PER_DAY, limit - len(items)))
        )).scalars().all() if seen else (await db.execute(
            select(Question).order_by(Question.id).limit(min(NEW_PER_DAY, limit - len(items)))
        )).scalars().all()
        for q in new_qs:
            items.append(_q(q, now, 0, 0))

    return {"items": items, "engine": srs.engine_name()}


@router.post("/grade")
async def grade_card(data: ReviewGradeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    q_exists = (await db.execute(
        select(Question.id).where(Question.id == data.question_id)
    )).scalar_one_or_none()
    if not q_exists:
        raise HTTPException(status_code=404, detail="Question not found")
    card = (await db.execute(
        select(ReviewCard).where(ReviewCard.user_id == user.id, ReviewCard.question_id == data.question_id)
    )).scalar_one_or_none()
    if card is None:
        card = ReviewCard(user_id=user.id, question_id=data.question_id, fsrs_state="")
        db.add(card)

    res = srs.review(card.fsrs_state or None, data.rating, now)
    card.due = res.due
    card.fsrs_state = res.blob
    card.state = res.state
    card.last_review = now
    card.reps = (card.reps or 0) + 1
    if res.is_lapse:
        card.lapses = (card.lapses or 0) + 1

    db.add(ReviewLog(user_id=user.id, question_id=data.question_id, rating=data.rating, reviewed_at=now))
    touch_streak(user)
    await db.commit()
    return {"ok": True, "due": card.due, "state": card.state, "reps": card.reps}


@router.get("/stats", response_model=ReviewStats)
async def stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    today = now.date()
    due_now = (await db.execute(
        select(func.count(ReviewCard.id)).where(ReviewCard.user_id == user.id, ReviewCard.due <= now)
    )).scalar() or 0
    total_cards = (await db.execute(
        select(func.count(ReviewCard.id)).where(ReviewCard.user_id == user.id)
    )).scalar() or 0
    total_q = (await db.execute(select(func.count(Question.id)))).scalar() or 0
    logs_today = (await db.execute(
        select(ReviewLog.reviewed_at).where(ReviewLog.user_id == user.id)
    )).scalars().all()
    reviewed_today = sum(1 for r in logs_today if r and r.date() == today)
    return ReviewStats(
        due_now=due_now, new_available=max(0, total_q - total_cards),
        reviewed_today=reviewed_today, total_cards=total_cards,
    )
