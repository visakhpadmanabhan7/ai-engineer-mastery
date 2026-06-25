from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import Lesson, Progress, User
from ..schemas import ProgressIn, ProgressOut
from ..services.activity import touch_streak

router = APIRouter(prefix="/api/progress", tags=["progress"])


async def _progress_payload(user: User, db: AsyncSession) -> ProgressOut:
    rows = (await db.execute(
        select(Lesson.day).join(Progress, Progress.lesson_id == Lesson.id).where(
            Progress.user_id == user.id, Progress.status == "completed"
        )
    )).scalars().all()
    total = (await db.execute(select(func.count(Lesson.id)))).scalar() or 0
    days = sorted(rows)
    pct = round(100 * len(days) / total, 1) if total else 0.0
    return ProgressOut(completed_days=days, total=total, pct=pct, current_streak=user.current_streak)


@router.get("", response_model=ProgressOut)
async def get_progress(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _progress_payload(user, db)


@router.post("", response_model=ProgressOut)
async def set_progress(data: ProgressIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(Progress).where(Progress.user_id == user.id, Progress.lesson_id == data.lesson_id)
    )).scalar_one_or_none()
    if data.completed:
        lesson_exists = (await db.execute(
            select(Lesson.id).where(Lesson.id == data.lesson_id)
        )).scalar_one_or_none()
        if not lesson_exists:
            raise HTTPException(status_code=404, detail="Lesson not found")
        if row is None:
            row = Progress(user_id=user.id, lesson_id=data.lesson_id)
            db.add(row)
        row.status = "completed"
        row.completed_at = datetime.now(timezone.utc)
        row.time_spent_seconds = (row.time_spent_seconds or 0) + max(0, data.time_spent_seconds)
        touch_streak(user)
    elif row is not None:
        await db.delete(row)
    await db.commit()
    await db.refresh(user)
    return await _progress_payload(user, db)
