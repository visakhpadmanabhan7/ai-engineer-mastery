"""Ingest the static learning-path content into the database.

- Modules + 68 lessons (parsed from learning-path/modules/**/*.html)
- The spaced-repetition question deck (parsed from learning-path/question-bank.html)

Idempotent: lessons/modules are upserted by slug/day; questions seed once.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Lesson, Module, Question

log = logging.getLogger("app.ingest")

MODULES = [
    (1, "m01-llm-foundations", "LLM Foundations", "Week 1", False),
    (2, "m02-prompting-context", "Prompting & Context Engineering", "Week 2", False),
    (3, "m03-rag-retrieval", "RAG & Retrieval", "Weeks 3-4", True),
    (4, "m04-agents", "Agents & Tool Use", "Weeks 5-6", True),
    (5, "m05-evaluation", "Evaluation & Observability", "Week 7", True),
    (6, "m06-finetuning", "Fine-tuning & Model Adaptation", "Week 8", False),
    (7, "m07-llmops-serving", "LLMOps, Serving & Optimization", "Week 9", False),
    (8, "m08-system-design-fundamentals", "System Design Fundamentals", "Week 10", False),
    (9, "m09-ml-system-design", "ML System Design", "Week 11", False),
    (10, "m10-genai-system-design", "GenAI System Design", "Week 12", True),
    (11, "m11-interview-mastery", "Interview Mastery & Capstone", "Week 13", False),
]

TOPIC_TO_MODULE = {
    "foundations": 1, "prompting": 2, "rag": 3, "agents": 4, "eval": 5,
    "finetune": 6, "llmops": 7, "backend": 7, "sysdesign": 8,
    "livecoding": 4, "behavioral": 11, "askback": 11,
}


def _parse_lesson(path: Path, module_number: int) -> dict | None:
    m = re.search(r"d(\d\d)-(.+)\.html$", path.name)
    if not m:
        return None
    day = int(m.group(1))
    slug = f"d{m.group(1)}-{m.group(2)}"
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else path.stem
    lede = soup.find("p", class_="lede")
    summary = lede.get_text(" ", strip=True) if lede else ""

    wrap = soup.find("div", class_="wrap")
    est, diff = 50, 1
    if wrap:
        meta = wrap.find("div", class_="meta-row")
        if meta:
            tmin = re.search(r"(\d+)\s*min", meta.get_text(" ", strip=True))
            if tmin:
                est = int(tmin.group(1))
            d = meta.find("span", class_="diff")
            if d:
                diff = max(1, len(d.find_all("i", class_="on")))
        # strip the bits the app renders itself
        for cls in ("complete-bar", "lesson-nav", "foot"):
            for el in wrap.find_all(class_=cls):
                el.decompose()
        for el in wrap.find_all("div", id="completeBar"):
            el.decompose()
        body_html = wrap.decode_contents()
    else:
        body_html = ""

    return {
        "day": day, "slug": slug, "title": title, "summary": summary,
        "est_minutes": est, "difficulty": diff, "module_number": module_number,
        "body_html": body_html,
    }


def parse_lessons(content_dir: Path) -> list[dict]:
    out: list[dict] = []
    for num, mslug, *_ in MODULES:
        mdir = content_dir / "modules" / mslug
        if not mdir.is_dir():
            continue
        for f in sorted(mdir.glob("d*.html")):
            rec = _parse_lesson(f, num)
            if rec:
                out.append(rec)
    return out


def parse_questions(content_dir: Path) -> list[dict]:
    qb = content_dir / "question-bank.html"
    if not qb.is_file():
        return []
    soup = BeautifulSoup(qb.read_text(encoding="utf-8"), "html.parser")
    out: list[dict] = []
    for section in soup.find_all("h2", id=True):
        topic = section.get("id")
        # the q-list immediately following this heading (until the next h2)
        node = section.find_next_sibling()
        while node is not None and node.name != "h2":
            if node.name == "ul" and "q-list" in (node.get("class") or []):
                for li in node.find_all("li", recursive=False):
                    ans_el = li.find("div", class_="a")
                    answer = ""
                    if ans_el:
                        answer = re.sub(r"^Key:\s*", "", ans_el.get_text(" ", strip=True))
                        ans_el.extract()
                    prompt = li.get_text(" ", strip=True)
                    if prompt:
                        out.append({
                            "topic": topic, "prompt": prompt, "answer_key": answer,
                            "module_number": TOPIC_TO_MODULE.get(topic),
                            "difficulty": 2,
                        })
                break
            node = node.find_next_sibling()
    return out


async def ingest_all(db: AsyncSession) -> dict:
    content = settings.content_path
    log.info("ingesting content from %s", content)

    # modules (upsert by slug)
    by_number: dict[int, Module] = {}
    for num, slug, title, week, core in MODULES:
        mod = (await db.execute(select(Module).where(Module.slug == slug))).scalar_one_or_none()
        if mod is None:
            mod = Module(slug=slug, number=num, title=title, week=week, is_core=core)
            db.add(mod)
        else:
            mod.number, mod.title, mod.week, mod.is_core = num, title, week, core
        by_number[num] = mod
    await db.flush()

    # lessons (upsert by day)
    lessons = parse_lessons(content)
    for rec in lessons:
        les = (await db.execute(select(Lesson).where(Lesson.day == rec["day"]))).scalar_one_or_none()
        mod = by_number.get(rec["module_number"])
        if mod is None:
            continue
        if les is None:
            les = Lesson(day=rec["day"], slug=rec["slug"], module_id=mod.id)
            db.add(les)
        les.slug = rec["slug"]
        les.title = rec["title"]
        les.summary = rec["summary"]
        les.est_minutes = rec["est_minutes"]
        les.difficulty = rec["difficulty"]
        les.body_html = rec["body_html"]
        les.module_id = mod.id

    # questions (seed once)
    qcount = (await db.execute(select(func.count(Question.id)))).scalar() or 0
    seeded = 0
    if qcount == 0:
        for q in parse_questions(content):
            mod = by_number.get(q["module_number"]) if q["module_number"] else None
            db.add(Question(
                topic=q["topic"], prompt=q["prompt"], answer_key=q["answer_key"],
                difficulty=q["difficulty"], source="notion",
                module_id=mod.id if mod else None,
            ))
            seeded += 1

    await db.commit()
    result = {"modules": len(MODULES), "lessons": len(lessons), "questions_seeded": seeded}
    log.info("ingest complete: %s", result)
    return result
