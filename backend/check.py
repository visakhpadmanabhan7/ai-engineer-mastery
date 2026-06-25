"""In-process smoke test: boots the app (runs lifespan: ingest + seed) and
exercises the core flows. Run: PYTHONPATH=backend .venv/bin/python backend/check.py
"""
import sys
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import User
from app.services.activity import touch_streak

ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


with TestClient(app) as c:  # context manager triggers startup (ingest + seed)
    check("health", c.get("/api/health").json().get("status") == "ok")

    meta = c.get("/api/meta").json()
    check("meta lessons", meta.get("lessons", 0) >= 60, f"(lessons={meta.get('lessons')})")
    check("meta questions", meta.get("questions", 0) >= 40, f"(questions={meta.get('questions')})")
    print(f"        engine={meta.get('srs_engine')} ai={meta.get('ai_enabled')} db={meta.get('db')}")

    # auth: seed login
    r = c.post("/api/auth/login", data={"username": "visakh@local", "password": "learn"})
    check("seed login", r.status_code == 200, f"(status={r.status_code})")
    token = r.json().get("access_token", "")
    h = {"Authorization": f"Bearer {token}"}

    # register a fresh user too
    import time
    email = f"test{int(time.time())}@x.io"
    rr = c.post("/api/auth/register", json={"email": email, "password": "pw1234", "display_name": "Test"})
    check("register", rr.status_code == 200, f"(status={rr.status_code})")

    me = c.get("/api/auth/me", headers=h).json()
    check("me", me.get("email") == "visakh@local")

    cur = c.get("/api/curriculum", headers=h).json()
    nmods = len(cur)
    nles = sum(len(m["lessons"]) for m in cur)
    check("curriculum", nmods == 11 and nles >= 60, f"(modules={nmods} lessons={nles})")

    les = c.get("/api/lessons/13", headers=h).json()
    check("lesson body", len(les.get("body_html", "")) > 500, f"(title='{les.get('title')}')")

    # progress
    lid = cur[0]["lessons"][0]["id"]
    p = c.post("/api/progress", headers=h, json={"lesson_id": lid, "completed": True}).json()
    check("mark complete", 1 in p.get("completed_days", []), f"(pct={p.get('pct')})")

    # review / SRS
    q = c.get("/api/review/queue?limit=10", headers=h).json()
    items = q.get("items", [])
    check("review queue", len(items) > 0, f"(items={len(items)} engine={q.get('engine')})")
    if items:
        qid = items[0]["question"]["id"]
        g = c.post("/api/review/grade", headers=h, json={"question_id": qid, "rating": 3})
        check("grade card (FSRS)", g.status_code == 200 and g.json().get("ok"), f"(due={g.json().get('due')})")
    st = c.get("/api/review/stats", headers=h).json()
    check("review stats", "due_now" in st, f"(total_cards={st.get('total_cards')})")

    # input validation: unknown ids are rejected cleanly (404), not 500 / silent orphan
    bad_p = c.post("/api/progress", headers=h, json={"lesson_id": 999999, "completed": True})
    check("reject bad lesson_id", bad_p.status_code == 404, f"(status={bad_p.status_code})")
    bad_g = c.post("/api/review/grade", headers=h, json={"question_id": 999999, "rating": 3})
    check("reject bad question_id", bad_g.status_code == 404, f"(status={bad_g.status_code})")

    # notes
    n = c.post("/api/notes", headers=h, json={"content": "RRF is rank-only fusion.", "lesson_id": None})
    check("create note", n.status_code == 200)

    # tutor (no key -> graceful)
    tu = c.get("/api/tutor/status", headers=h).json()
    check("tutor status", "ai_enabled" in tu)
    gr = c.post("/api/tutor/grade", headers=h, json={"kind": "grade", "message": "What is BM25?", "user_answer": "lexical"})
    check("tutor grade endpoint", gr.status_code == 200, f"(degraded={gr.json().get('feedback','')[:40]!r})")

    # analytics
    an = c.get("/api/analytics", headers=h).json()
    check("analytics", an.get("lessons_total", 0) >= 60, f"(completed={an.get('lessons_completed')})")

    # new subsystems: embeddings/memory/cache in meta, semantic search, usage tracing + grade cache
    m2 = c.get("/api/meta").json()
    check("meta embeddings/memory/cache",
          all(m2.get(k) for k in ("embeddings", "memory", "cache")),
          f"(embeddings={m2.get('embeddings')} memory={m2.get('memory')} cache={m2.get('cache')})")
    sr = c.post("/api/search", headers=h, json={"query": "evaluate a RAG retriever", "k": 5}).json()
    check("semantic search", len(sr.get("results", [])) > 0, f"(mode={sr.get('mode')} n={len(sr.get('results', []))})")
    qb = c.get("/api/questions", headers=h).json()
    check("question bank", qb.get("total", 0) >= 100 and len(qb.get("topics", [])) >= 5,
          f"(total={qb.get('total')} topics={len(qb.get('topics', []))})")
    check("usage endpoint", c.get("/api/usage", headers=h).status_code == 200)
    if m2.get("ai_enabled"):
        qa = {"kind": "grade", "message": "What is RRF?", "user_answer": "Reciprocal rank fusion."}
        c.post("/api/tutor/grade", headers=h, json=qa)
        c.post("/api/tutor/grade", headers=h, json=qa)  # identical -> cache hit
        usg = c.get("/api/usage", headers=h).json()
        check("usage traced", usg.get("calls", 0) >= 1, f"(calls={usg.get('calls')} tokens={usg.get('total_tokens')})")
        check("grade cache hit", usg.get("cache_hits", 0) >= 1, f"(cache_hits={usg.get('cache_hits')})")

# streak logic: day-boundary correctness (pure, no HTTP)
su = User(); su.current_streak = 0; su.longest_streak = 0; su.last_active_date = None
d0 = date(2026, 1, 1)
touch_streak(su, d0); touch_streak(su, d0)            # two lessons same day
check("streak same-day = 1", su.current_streak == 1, f"({su.current_streak})")
touch_streak(su, d0 + timedelta(days=1))             # consecutive day
check("streak consecutive +1", su.current_streak == 2, f"({su.current_streak})")
touch_streak(su, d0 + timedelta(days=3))             # skipped a day
check("streak gap resets to 1", su.current_streak == 1, f"({su.current_streak})")
check("streak longest tracked", su.longest_streak == 2, f"({su.longest_streak})")

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
