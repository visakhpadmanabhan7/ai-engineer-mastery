"""SQLAlchemy 2.0 ORM models.

Embeddings use a portable Vector type: real pgvector on Postgres (HNSW-indexable),
JSON text on SQLite, so the same models run in both modes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

EMBED_DIM = 384  # all-MiniLM-L6-v2 (sentence-transformers)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Vector(TypeDecorator):
    """pgvector on Postgres, JSON-encoded list on SQLite. Same Python interface."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = EMBED_DIM, **kw):
        self.dim = dim
        super().__init__(**kw)

    def _use_pg(self, dialect) -> bool:
        if dialect.name != "postgresql":
            return False
        from . import database

        return getattr(database, "PGVECTOR_OK", False)

    def load_dialect_impl(self, dialect):
        if self._use_pg(dialect):
            from pgvector.sqlalchemy import Vector as PGVector

            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if self._use_pg(dialect):
            return list(value)
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if self._use_pg(dialect):
            return list(value)
        return json.loads(value)


# ---------------------------------------------------------------- users

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="Learner")
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # streak / habit tracking
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_goal_lessons: Mapped[int] = mapped_column(Integer, default=1)

    progress: Mapped[list["Progress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    cards: Mapped[list["ReviewCard"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# ---------------------------------------------------------------- content

class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    week: Mapped[str] = mapped_column(String(40), default="")
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="module", order_by="Lesson.day")


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    day: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"))
    title: Mapped[str] = mapped_column(String(200))
    est_minutes: Mapped[int] = mapped_column(Integer, default=50)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    body_html: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    embedding = mapped_column(Vector(), nullable=True)

    module: Mapped["Module"] = relationship(back_populates="lessons")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(80), index=True)
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id"), nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    answer_key: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    source: Mapped[str] = mapped_column(String(40), default="notion")


# ---------------------------------------------------------------- progress

class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_progress_user_lesson"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")  # in_progress|completed
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="progress")


# ---------------------------------------------------------------- spaced repetition (FSRS)

class ReviewCard(Base):
    """Per-user FSRS state for one question. Serialized FSRS Card fields."""

    __tablename__ = "review_cards"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_card_user_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)

    # FSRS state: `due` is broken out (indexed) for the review-queue query; the full
    # FSRS Card is round-tripped via JSON in `fsrs_state` so we stay version-tolerant.
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    fsrs_state: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[int] = mapped_column(Integer, default=0)  # 0=new 1=learning 2=review 3=relearning
    last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="cards")


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    rating: Mapped[int] = mapped_column(Integer)  # 1 again 2 hard 3 good 4 easy
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- notes (RAG source)

class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    embedding = mapped_column(Vector(), nullable=True)


# ---------------------------------------------------------------- AI tutor

class TutorSession(Base):
    __tablename__ = "tutor_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="chat")  # deepen|grade|mock|chat
    title: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["TutorMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="TutorMessage.id"
    )


class TutorMessage(Base):
    __tablename__ = "tutor_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("tutor_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped["TutorSession"] = relationship(back_populates="messages")


class Attempt(Base):
    """A graded answer (practice, AI grade, or mock round) — powers weak-area analytics."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"), nullable=True)
    topic: Mapped[str] = mapped_column(String(80), default="", index=True)
    kind: Mapped[str] = mapped_column(String(20), default="grade")  # grade|mock|practice
    user_answer: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    feedback: Mapped[str] = mapped_column(Text, default="")
    model_answer: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- observability

class LlmTrace(Base):
    """One LLM call: tokens, estimated cost, latency, provider/model (observability)."""

    __tablename__ = "llm_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # tutor | grade | embed
    provider: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
