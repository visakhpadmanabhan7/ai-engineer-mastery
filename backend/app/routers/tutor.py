from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import get_current_user
from ..models import Attempt, Lesson, Note, TutorMessage, TutorSession, User
from ..schemas import GradeOut, TutorAskIn, TutorMessageOut, TutorSessionOut
from ..services import ai
from ..services.ratelimit import SlidingWindowLimiter

router = APIRouter(prefix="/api/tutor", tags=["tutor"])

# Per-user cap on calls that hit the LLM provider (protects the owner's API key
# on a public instance). In-memory / per-process; see services/ratelimit.py.
_ai_limiter = SlidingWindowLimiter(settings.ai_rate_per_min, 60.0)


def _rate_limit(user: User) -> None:
    if not _ai_limiter.allow(str(user.id)):
        raise HTTPException(status_code=429, detail="Too many tutor requests; please wait a moment.")


async def _valid_lesson_id(db: AsyncSession, lesson_id: int | None) -> int | None:
    """Coerce an unknown lesson_id to None so an optional lesson reference never
    triggers a foreign-key error when the row is persisted."""
    if lesson_id is None:
        return None
    ok = (await db.execute(select(Lesson.id).where(Lesson.id == lesson_id))).scalar_one_or_none()
    return lesson_id if ok else None


async def _build_context(db: AsyncSession, user: User, lesson_id: int | None) -> str:
    parts: list[str] = []
    if lesson_id:
        lesson = (await db.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one_or_none()
        if lesson:
            parts.append(f"Current lesson: Day {lesson.day} — {lesson.title}. {lesson.summary}")
    notes = (await db.execute(
        select(Note).where(Note.user_id == user.id).order_by(Note.id.desc()).limit(5)
    )).scalars().all()
    if notes:
        parts.append("Learner's recent notes:\n" + "\n".join(f"- {n.content[:300]}" for n in notes))
    return "\n\n".join(parts)


@router.post("/chat")
async def chat(data: TutorAskIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _rate_limit(user)
    kind = data.kind if data.kind in ("deepen", "mock", "chat") else "chat"
    lesson_id = await _valid_lesson_id(db, data.lesson_id)
    context = await _build_context(db, user, lesson_id)

    # resolve / create session
    session = None
    if data.session_id:
        session = (await db.execute(
            select(TutorSession).where(TutorSession.id == data.session_id, TutorSession.user_id == user.id)
        )).scalar_one_or_none()
    if session is None:
        session = TutorSession(
            user_id=user.id, lesson_id=lesson_id, kind=kind,
            title=(data.message[:60] or kind.title()),
        )
        db.add(session)
        await db.flush()
    session_id = session.id

    # prior turns for multi-turn coherence
    prior = (await db.execute(
        select(TutorMessage).where(TutorMessage.session_id == session_id).order_by(TutorMessage.id)
    )).scalars().all()
    api_messages = [{"role": m.role, "content": m.content} for m in prior]
    api_messages.append({"role": "user", "content": data.message})

    db.add(TutorMessage(session_id=session_id, role="user", content=data.message))
    await db.commit()

    system = ai.system_for(kind, context)

    async def gen():
        acc: list[str] = []
        async for chunk in ai.stream_chat(system, api_messages):
            acc.append(chunk)
            yield chunk
        # persist assistant message with a fresh session (request session is closing)
        async with SessionLocal() as s2:
            s2.add(TutorMessage(session_id=session_id, role="assistant", content="".join(acc)))
            await s2.commit()

    return StreamingResponse(
        gen(), media_type="text/plain; charset=utf-8",
        headers={"X-Session-Id": str(session_id), "X-Accel-Buffering": "no"},
    )


@router.post("/grade", response_model=GradeOut)
async def grade(data: TutorAskIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _rate_limit(user)
    question = data.question or data.message
    answer = data.user_answer or ""
    lesson_id = await _valid_lesson_id(db, data.lesson_id)
    res = await ai.grade(question, answer)
    db.add(Attempt(
        user_id=user.id, question_id=None, lesson_id=lesson_id,
        topic=(data.kind if data.kind not in ("grade", "chat") else ""),
        kind="grade", user_answer=answer, score=res["score"],
        feedback=res["feedback"], model_answer=res["model_answer"],
    ))
    await db.commit()
    return GradeOut(
        score=res["score"] if res["score"] is not None else 0.0,
        feedback=res["feedback"], model_answer=res["model_answer"], one_fix=res["one_fix"],
    )


@router.get("/sessions", response_model=list[TutorSessionOut])
async def sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(TutorSession).where(TutorSession.user_id == user.id).order_by(TutorSession.id.desc()).limit(50)
    )).scalars().all()
    return rows


@router.get("/sessions/{sid}/messages", response_model=list[TutorMessageOut])
async def session_messages(sid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    owns = (await db.execute(
        select(TutorSession.id).where(TutorSession.id == sid, TutorSession.user_id == user.id)
    )).scalar_one_or_none()
    if not owns:
        return []
    rows = (await db.execute(
        select(TutorMessage).where(TutorMessage.session_id == sid).order_by(TutorMessage.id)
    )).scalars().all()
    return rows


@router.get("/status")
async def status(user: User = Depends(get_current_user)):
    info = ai.provider_info()
    return {"ai_enabled": info["enabled"], "provider": info["provider"], "model": info["model"]}
