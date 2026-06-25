"""Tutor conversation memory, managed with LangChain.

Trims prior turns to a bounded window (LangChain `trim_messages`) so long chats
stay within the context budget while keeping the most recent, coherent history.
Falls back to a simple last-N slice if langchain-core is not installed.
"""
from __future__ import annotations

import logging

from ..config import settings

log = logging.getLogger("app.memory")


def engine() -> str:
    try:
        import langchain_core  # noqa: F401

        return "langchain"
    except Exception:
        return "slice"


def window(messages: list[dict], max_messages: int | None = None) -> list[dict]:
    """`messages`: [{'role': 'user'|'assistant', 'content': str}, ...] in order.

    Returns the trimmed tail that should be sent to the model, always starting on
    a user turn so the provider APIs accept it.
    """
    limit = max_messages or settings.tutor_history_messages
    if len(messages) <= limit:
        return messages
    try:
        from langchain_core.messages import AIMessage, HumanMessage, trim_messages

        lc = [
            HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
            for m in messages
        ]
        trimmed = trim_messages(
            lc,
            max_tokens=limit,
            strategy="last",
            token_counter=len,          # count by message; provider-agnostic
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
        out = [
            {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
            for m in trimmed
        ]
        return out or messages[-limit:]
    except Exception as exc:  # pragma: no cover - depends on optional dep
        log.info("langchain trim unavailable (%s); slice fallback", exc)
        return messages[-limit:]
