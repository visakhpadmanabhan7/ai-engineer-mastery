from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Lesson, Module, Progress, User
from ..schemas import LessonDetail, ModuleWithLessons

router = APIRouter(prefix="/api", tags=["content"])


@router.get("/curriculum", response_model=list[ModuleWithLessons])
async def curriculum(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    mods = (
        await db.execute(
            select(Module).options(selectinload(Module.lessons)).order_by(Module.number)
        )
    ).scalars().all()
    done = set(
        (await db.execute(
            select(Progress.lesson_id).where(
                Progress.user_id == user.id, Progress.status == "completed"
            )
        )).scalars().all()
    )
    out = []
    for m in mods:
        lessons = [
            {
                "id": l.id, "day": l.day, "slug": l.slug, "title": l.title,
                "est_minutes": l.est_minutes, "difficulty": l.difficulty,
                "module_id": l.module_id, "completed": l.id in done,
            }
            for l in sorted(m.lessons, key=lambda x: x.day)
        ]
        out.append({
            "id": m.id, "slug": m.slug, "number": m.number, "title": m.title,
            "week": m.week, "is_core": m.is_core, "lessons": lessons,
        })
    return out


@router.get("/lessons/{day}", response_model=LessonDetail)
async def get_lesson(day: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    lesson = (await db.execute(select(Lesson).where(Lesson.day == day))).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson
