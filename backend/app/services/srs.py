"""Spaced-repetition scheduling.

Primary: FSRS-6 via the `fsrs` library (state-of-the-art, 2026). If the installed
API differs or the import fails, a compact SM-2-style fallback keeps the app working.
Persistence is version-tolerant: the whole scheduler state is round-tripped as JSON.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

log = logging.getLogger("app.srs")

_HAVE_FSRS = False
try:  # pragma: no cover - import shape varies by version
    from fsrs import Card, Rating, Scheduler

    _scheduler = Scheduler()
    _HAVE_FSRS = True
    log.info("FSRS engine active (fsrs library)")
except Exception as exc:  # pragma: no cover
    log.warning("fsrs unavailable (%s); using SM-2 fallback", exc)


@dataclass
class CardState:
    due: datetime
    state: int
    blob: str
    is_lapse: bool = False


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ----------------------------------------------------------------- FSRS path
def _fsrs_dump(card) -> CardState:
    d = card.to_dict()
    st = card.state.value if hasattr(card.state, "value") else int(card.state)
    return CardState(due=_aware(card.due), state=int(st), blob=json.dumps(d, default=str))


def _fsrs_new() -> CardState:
    return _fsrs_dump(Card())


def _fsrs_review(blob: str, rating: int, now: datetime) -> CardState:
    card = Card.from_dict(json.loads(blob)) if blob else Card()
    new_card, _logentry = _scheduler.review_card(card, Rating(rating), now)
    out = _fsrs_dump(new_card)
    out.is_lapse = rating == 1
    return out


# ----------------------------------------------------------------- SM-2 fallback
def _sm2_new() -> CardState:
    now = datetime.now(timezone.utc)
    return CardState(due=now, state=0, blob=json.dumps({"ef": 2.5, "interval": 0, "reps": 0}))


def _sm2_review(blob: str, rating: int, now: datetime) -> CardState:
    s = json.loads(blob) if blob else {"ef": 2.5, "interval": 0, "reps": 0}
    q = {1: 2, 2: 3, 3: 4, 4: 5}[rating]  # map 4-button to SM-2 quality
    ef = max(1.3, s["ef"] + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    if rating == 1:
        reps, interval = 0, 0
    else:
        reps = s["reps"] + 1
        interval = 1 if reps == 1 else (6 if reps == 2 else round(s["interval"] * ef))
    due = now + timedelta(days=max(interval, 0), minutes=10 if interval == 0 else 0)
    state = 2 if reps >= 2 else 1
    return CardState(
        due=due, state=state,
        blob=json.dumps({"ef": ef, "interval": interval, "reps": reps}),
        is_lapse=rating == 1,
    )


# ----------------------------------------------------------------- public API
def new_card() -> CardState:
    return _fsrs_new() if _HAVE_FSRS else _sm2_new()


def review(blob: str | None, rating: int, now: datetime | None = None) -> CardState:
    now = now or datetime.now(timezone.utc)
    if _HAVE_FSRS:
        try:
            return _fsrs_review(blob or "", rating, now)
        except Exception as exc:  # pragma: no cover
            log.warning("FSRS review failed (%s); falling back", exc)
    return _sm2_review(blob or "", rating, now)


def engine_name() -> str:
    return "FSRS-6" if _HAVE_FSRS else "SM-2 (fallback)"
