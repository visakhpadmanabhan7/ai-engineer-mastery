"""Provider-agnostic AI tutor: streamed teaching/mock + structured grading.

Supports two backends, chosen by `LLM_PROVIDER` (or auto-detected from whichever
key is set):
  - anthropic : Claude (Opus 4.8 tutor, Haiku 4.5 judge)
  - groq      : any OpenAI-compatible endpoint (Groq by default; free tier)

Every call is traced (tokens / est. cost / latency, see services/tracing) and
grading results are cached (services/cache). Degrades gracefully with no key.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator

from ..config import settings
from . import cache, tracing

log = logging.getLogger("app.ai")

_anthropic_client = None
_openai_client = None


def provider() -> str:
    return settings.resolved_provider


def ai_available() -> bool:
    return settings.ai_enabled


def _tutor_model() -> str:
    return settings.tutor_model if provider() == "anthropic" else settings.groq_model


def _judge_model() -> str:
    return settings.judge_model if provider() == "anthropic" else settings.groq_judge_model


def provider_info() -> dict:
    p = provider()
    model = {"anthropic": settings.tutor_model, "groq": settings.groq_model}.get(p, "")
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
async def stream_chat(system: str, messages: list[dict], *, user_id: int | None = None) -> AsyncIterator[str]:
    p = provider()
    if p == "none":
        yield (
            "The live AI tutor is not configured. Set ANTHROPIC_API_KEY (Claude) or GROQ_API_KEY "
            "(free) in backend/.env to enable streamed teaching, mock interviews, and grading. "
            "Everything else in the app works without it."
        )
        return

    t0 = time.monotonic()
    pin = pout = 0
    model = _tutor_model()
    try:
        if p == "anthropic":
            client = _anthropic()
            async with client.messages.stream(
                model=model, max_tokens=2000, system=system, messages=messages
            ) as stream:
                async for text in stream.text_stream:
                    yield text
                try:
                    final = await stream.get_final_message()
                    pin, pout = final.usage.input_tokens, final.usage.output_tokens
                except Exception:  # pragma: no cover
                    pass
        else:  # groq / openai-compatible
            client = _openai()
            oai_messages = [{"role": "system", "content": system}, *messages]
            stream = await client.chat.completions.create(
                model=model, messages=oai_messages, max_tokens=2000,
                stream=True, stream_options={"include_usage": True},
            )
            async for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage:
                    pin = getattr(usage, "prompt_tokens", 0) or 0
                    pout = getattr(usage, "completion_tokens", 0) or 0
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
    except Exception:  # pragma: no cover - network/runtime
        log.exception("tutor stream failed")
        yield (
            "\n\n[tutor error: the request to the AI provider failed. Check the server logs "
            "and your API key / model access.]"
        )
    finally:
        await tracing.record(
            kind="tutor", provider=p, model=model,
            prompt_tokens=pin, completion_tokens=pout,
            latency_ms=int((time.monotonic() - t0) * 1000), user_id=user_id,
        )


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


async def grade(question: str, answer: str, *, user_id: int | None = None) -> dict:
    p = provider()
    if p == "none":
        return {
            "score": None,
            "feedback": "Set ANTHROPIC_API_KEY or GROQ_API_KEY to enable AI grading.",
            "one_fix": "",
            "model_answer": "",
        }

    model = _judge_model()
    key = "grade:" + hashlib.sha256(f"{model}|{question}|{answer}".encode("utf-8")).hexdigest()
    cached = await cache.get(key)
    if cached is not None:
        await tracing.record(kind="grade", provider=p, model=model, cache_hit=True, user_id=user_id)
        return cached

    t0 = time.monotonic()
    pin = pout = 0
    user = f"QUESTION:\n{question}\n\nCANDIDATE ANSWER:\n{answer}"
    try:
        if p == "anthropic":
            client = _anthropic()
            msg = await client.messages.create(
                model=model, max_tokens=1200, system=GRADE_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            pin, pout = msg.usage.input_tokens, msg.usage.output_tokens
        else:  # groq / openai-compatible
            client = _openai()
            resp = await client.chat.completions.create(
                model=model, max_tokens=1200,
                response_format={"type": "json_object"},  # force valid, complete JSON
                messages=[{"role": "system", "content": GRADE_SYSTEM}, {"role": "user", "content": user}],
            )
            text = resp.choices[0].message.content or ""
            if resp.usage:
                pin, pout = resp.usage.prompt_tokens, resp.usage.completion_tokens
        result = _normalize_grade(_extract_json(text), text)
        await cache.set(key, result)
        return result
    except Exception:  # pragma: no cover
        log.exception("grade failed")
        return {
            "score": None,
            "feedback": "Grading failed due to an AI provider error. Check the server logs.",
            "one_fix": "",
            "model_answer": "",
        }
    finally:
        await tracing.record(
            kind="grade", provider=p, model=model,
            prompt_tokens=pin, completion_tokens=pout,
            latency_ms=int((time.monotonic() - t0) * 1000), user_id=user_id,
        )
