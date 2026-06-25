"""Provider-agnostic AI tutor: streamed teaching/mock + structured grading.

Supports two backends, chosen by `LLM_PROVIDER` (or auto-detected from whichever
key is set):
  - anthropic : Claude (Opus 4.8 tutor, Haiku 4.5 judge)
  - groq      : any OpenAI-compatible endpoint (Groq by default; free tier)
Degrades gracefully when no key is configured.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

from ..config import settings

log = logging.getLogger("app.ai")

_anthropic_client = None
_openai_client = None


def provider() -> str:
    return settings.resolved_provider


def ai_available() -> bool:
    return settings.ai_enabled


def provider_info() -> dict:
    p = provider()
    model = {
        "anthropic": settings.tutor_model,
        "groq": settings.groq_model,
    }.get(p, "")
    return {"provider": p, "model": model, "enabled": p != "none"}


def _anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic

        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _openai():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI

        _openai_client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=settings.openai_base_url)
    return _openai_client


# ------------------------------------------------------------------ persona
VISAKH_CONTEXT = (
    "The learner is Visakh, an AI engineer (~3 years, currently core developer on MaiQ at "
    "MaindTec). Real, citable work you may reference to anchor explanations: an LLM-as-judge "
    "evaluation framework with 11+ retrieval/chunking experiments that cut inference cost 37% at "
    "a 2% retrieval-quality drop; hybrid retrieval (BM25 + dense, fused with RRF) into pgvector "
    "via FastAPI; the MaiQ Skill Store (users author their own agents in chat). He is preparing "
    "for senior AI Engineer / ML Engineer interviews in Europe."
)
VOICE = (
    "Voice: precise, senior, concrete. American English. No em-dashes. Prefer 'agentic "
    "application', 'context engineering', 'agentic retrieval'. Never fabricate facts about his "
    "work beyond those given."
)


def system_for(kind: str, context: str = "") -> str:
    base = f"You are an elite AI-engineering interview tutor. {VISAKH_CONTEXT} {VOICE}"
    ctx = f"\n\nRelevant lesson context and the learner's notes:\n{context}" if context else ""
    if kind == "deepen":
        return (
            base + " Teach actively, do not lecture. Explain the concept one level deeper than a "
            "textbook with exactly one vivid analogy, then ask the learner 2-3 probing questions "
            "ONE AT A TIME and wait. Push back when an answer is vague. Connect to his real work "
            "where it genuinely fits." + ctx
        )
    if kind == "mock":
        return (
            base + " Run a realistic senior-level mock interview. Ask ONE question at a time, "
            "escalate difficulty based on answers, probe for trade-offs and the option they ruled "
            "out, and do NOT reveal model answers until they respond. After ~5 questions, or when "
            "the learner says 'score me', give a crisp scorecard (per-dimension /10), their two "
            "weakest areas, and the single highest-leverage fix." + ctx
        )
    return (
        base + " Answer the learner's questions rigorously and concisely. Offer a worked example "
        "when it clarifies. If they are guessing, nudge with a hint before the full answer." + ctx
    )


# ------------------------------------------------------------------ streaming
async def stream_chat(system: str, messages: list[dict]) -> AsyncIterator[str]:
    p = provider()
    if p == "none":
        yield (
            "The live AI tutor is not configured. Set ANTHROPIC_API_KEY (Claude) or GROQ_API_KEY "
            "(free) in backend/.env to enable streamed teaching, mock interviews, and grading. "
            "Everything else in the app works without it."
        )
        return
    try:
        if p == "anthropic":
            client = _anthropic()
            async with client.messages.stream(
                model=settings.tutor_model, max_tokens=2000, system=system, messages=messages
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        else:  # groq / openai-compatible
            client = _openai()
            oai_messages = [{"role": "system", "content": system}, *messages]
            stream = await client.chat.completions.create(
                model=settings.groq_model, messages=oai_messages, max_tokens=2000, stream=True
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
    except Exception as exc:  # pragma: no cover - network/runtime
        log.exception("tutor stream failed")
        yield f"\n\n[tutor error: {exc}. Check your API key and model access.]"


# ------------------------------------------------------------------ grading
GRADE_SYSTEM = (
    "You are a senior interviewer at a top AI company grading a candidate's spoken answer. "
    + VISAKH_CONTEXT
    + " Be fair but exacting. Reward correctness, depth, structure, and naming trade-offs. "
    "Return ONLY a JSON object, no prose around it, with keys: "
    '"score" (number 0-10), "feedback" (2-3 sentences), "one_fix" (the single highest-leverage '
    'improvement), "model_answer" (a strong 90-second answer). ' + VOICE
)


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def _normalize_grade(data: dict, fallback_text: str) -> dict:
    score = data.get("score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    return {
        "score": score,
        "feedback": str(data.get("feedback", "") or fallback_text[:400]),
        "one_fix": str(data.get("one_fix", "")),
        "model_answer": str(data.get("model_answer", "")),
    }


async def grade(question: str, answer: str) -> dict:
    p = provider()
    if p == "none":
        return {
            "score": None,
            "feedback": "Set ANTHROPIC_API_KEY or GROQ_API_KEY to enable AI grading.",
            "one_fix": "",
            "model_answer": "",
        }
    user = f"QUESTION:\n{question}\n\nCANDIDATE ANSWER:\n{answer}"
    try:
        if p == "anthropic":
            client = _anthropic()
            msg = await client.messages.create(
                model=settings.judge_model, max_tokens=900, system=GRADE_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        else:  # groq / openai-compatible
            client = _openai()
            resp = await client.chat.completions.create(
                model=settings.groq_judge_model, max_tokens=900,
                messages=[{"role": "system", "content": GRADE_SYSTEM}, {"role": "user", "content": user}],
            )
            text = resp.choices[0].message.content or ""
        return _normalize_grade(_extract_json(text), text)
    except Exception as exc:  # pragma: no cover
        log.exception("grade failed")
        return {"score": None, "feedback": f"Grading error: {exc}", "one_fix": "", "model_answer": ""}
