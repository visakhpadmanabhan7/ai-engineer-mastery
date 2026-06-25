"""LLM usage / cost observability: aggregates over the trace table."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import LlmTrace, User
from ..services import cache

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def usage(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    where = LlmTrace.user_id == user.id
    calls = (await db.execute(select(func.count(LlmTrace.id)).where(where))).scalar() or 0
    tokens = (await db.execute(select(func.coalesce(func.sum(LlmTrace.total_tokens), 0)).where(where))).scalar() or 0
    cost = (await db.execute(select(func.coalesce(func.sum(LlmTrace.est_cost_usd), 0.0)).where(where))).scalar() or 0.0
    hits = (await db.execute(
        select(func.count(LlmTrace.id)).where(where, LlmTrace.cache_hit.is_(True))
    )).scalar() or 0
    by_model = (await db.execute(
        select(
            LlmTrace.model,
            func.count(LlmTrace.id),
            func.coalesce(func.sum(LlmTrace.total_tokens), 0),
            func.coalesce(func.sum(LlmTrace.est_cost_usd), 0.0),
        ).where(where).group_by(LlmTrace.model)
    )).all()
    return {
        "calls": calls,
        "total_tokens": int(tokens),
        "est_cost_usd": round(float(cost), 4),
        "cache_hits": hits,
        "cache_backend": cache.backend(),
        "by_model": [
            {"model": m or "(none)", "calls": c, "tokens": int(t), "cost_usd": round(float(co), 4)}
            for m, c, t, co in by_model
        ],
    }
