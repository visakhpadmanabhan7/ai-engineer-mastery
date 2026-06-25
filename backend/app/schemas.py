"""Pydantic v2 request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4, max_length=128)
    display_name: str = "Learner"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: str
    current_streak: int
    longest_streak: int
    daily_goal_lessons: int


# ---------- content
class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    number: int
    title: str
    week: str
    is_core: bool


class LessonCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    day: int
    slug: str
    title: str
    est_minutes: int
    difficulty: int
    module_id: int


class LessonDetail(LessonCard):
    body_html: str
    summary: str


class LessonWithProgress(LessonCard):
    completed: bool = False


class ModuleWithLessons(ModuleOut):
    lessons: list[LessonWithProgress] = []


# ---------- progress
class ProgressIn(BaseModel):
    lesson_id: int
    completed: bool = True
    time_spent_seconds: int = 0


class ProgressOut(BaseModel):
    completed_days: list[int]
    total: int
    pct: float
    current_streak: int


# ---------- review / SRS
class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic: str
    prompt: str
    answer_key: str
    difficulty: int


class ReviewCardOut(BaseModel):
    question: QuestionOut
    due: datetime
    state: int
    reps: int


class ReviewGradeIn(BaseModel):
    question_id: int
    rating: int = Field(ge=1, le=4)  # 1 again, 2 hard, 3 good, 4 easy


class ReviewStats(BaseModel):
    due_now: int
    new_available: int
    reviewed_today: int
    total_cards: int


# ---------- notes
class NoteIn(BaseModel):
    content: str = Field(min_length=1)
    lesson_id: int | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    content: str
    lesson_id: int | None
    created_at: datetime


# ---------- AI tutor
class TutorAskIn(BaseModel):
    kind: str = "chat"  # deepen|grade|mock|chat
    lesson_id: int | None = None
    session_id: int | None = None
    message: str
    # for grade mode:
    question: str | None = None
    user_answer: str | None = None
    # for mock mode:
    module_id: int | None = None


class TutorMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str


class TutorSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    lesson_id: int | None
    created_at: datetime


class GradeOut(BaseModel):
    score: float
    feedback: str
    model_answer: str
    one_fix: str = ""


# ---------- analytics
class TopicScore(BaseModel):
    topic: str
    avg_score: float
    attempts: int


class Analytics(BaseModel):
    lessons_completed: int
    lessons_total: int
    cards_due: int
    reviews_total: int
    attempts_total: int
    current_streak: int
    longest_streak: int
    avg_score: float | None
    weakest_topics: list[TopicScore]
    strongest_topics: list[TopicScore]
    activity: dict[str, int]  # date -> count (last 30 days)
