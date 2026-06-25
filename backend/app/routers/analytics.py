from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import Attempt, Lesson, Progress, ReviewCard, ReviewLog, User
from ..schemas import Analytics, TopicScore

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("", response_model=Analytics)
async def analytics(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)

    lessons_total = (await db.execute(select(func.count(Lesson.id)))).scalar() or 0
    lessons_completed = (await db.execute(
        select(func.count(Progress.id)).where(Progress.user_id == user.id, Progress.status == "completed")
    )).scalar() or 0
    cards_due = (await db.execute(
        select(func.count(ReviewCard.id)).where(ReviewCard.user_id == user.id, ReviewCard.due <= now)
    )).scalar() or 0
    reviews_total = (await db.execute(
        select(func.count(ReviewLog.id)).where(ReviewLog.user_id == user.id)
    )).scalar() or 0

    attempts = (await db.execute(select(Attempt).where(Attempt.user_id == user.id))).scalars().all()
    attempts_total = len(attempts)
    scored = [a for a in attempts if a.score is not None]
    avg_score = round(sum(a.score for a in scored) / len(scored), 1) if scored else None

    by_topic: dict[str, list[float]] = defaultdict(list)
    for a in scored:
        if a.topic:
            by_topic[a.topic].append(a.score)
    topic_scores = [
        TopicScore(topic=t, avg_score=round(sum(v) / len(v), 1), attempts=len(v))
        for t, v in by_topic.items()
    ]
    weakest = sorted(topic_scores, key=lambda x: x.avg_score)[:5]
    strongest = sorted(topic_scores, key=lambda x: -x.avg_score)[:5]

    # 30-day activity heatmap (reviews + lesson completions)
    floor = now - timedelta(days=30)
    activity: dict[str, int] = defaultdict(int)
    rlogs = (await db.execute(
        select(ReviewLog.reviewed_at).where(ReviewLog.user_id == user.id, ReviewLog.reviewed_at >= floor)
    )).scalars().all()
    for r in rlogs:
        if r:
            activity[r.date().isoformat()] += 1
    progs = (await db.execute(
        select(Progress.completed_at).where(
            Progress.user_id == user.id, Progress.completed_at.is_not(None), Progress.completed_at >= floor
        )
    )).scalars().all()
    for p in progs:
        if p:
            activity[p.date().isoformat()] += 1

    return Analytics(
        lessons_completed=lessons_completed, lessons_total=lessons_total,
        cards_due=cards_due, reviews_total=reviews_total, attempts_total=attempts_total,
        current_streak=user.current_streak, longest_streak=user.longest_streak,
        avg_score=avg_score, weakest_topics=weakest, strongest_topics=strongest,
        activity=dict(activity),
    )
