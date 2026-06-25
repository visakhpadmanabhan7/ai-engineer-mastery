"""Daily-streak bookkeeping (shared by progress + review)."""
from __future__ import annotations

from datetime import date, timedelta

from ..models import User


def touch_streak(user: User, today: date | None = None) -> None:
    from datetime import datetime, timezone

    today = today or datetime.now(timezone.utc).date()
    last = user.last_active_date
    if last == today:
        return
    if last == today - timedelta(days=1):
        user.current_streak += 1
    else:
        user.current_streak = 1
    user.last_active_date = today
    user.longest_streak = max(user.longest_streak or 0, user.current_streak)
