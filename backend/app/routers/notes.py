from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import Note, User
from ..schemas import NoteIn, NoteOut

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.post("", response_model=NoteOut)
async def create_note(data: NoteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    note = Note(user_id=user.id, lesson_id=data.lesson_id, content=data.content)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("", response_model=list[NoteOut])
async def list_notes(lesson_id: int | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = select(Note).where(Note.user_id == user.id)
    if lesson_id:
        q = q.where(Note.lesson_id == lesson_id)
    rows = (await db.execute(q.order_by(Note.id.desc()).limit(100))).scalars().all()
    return rows
