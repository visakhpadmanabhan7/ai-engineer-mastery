# CLAUDE.md — AI Engineer Mastery (web app)

Instructions for any future Claude session working in this repository.

## What this is
A full-stack web application that turns a 68-lesson AI-engineering + system-design curriculum into a real product: accounts, a database, an FSRS spaced-repetition engine, progress + streak tracking, weak-area analytics, and an **in-app AI tutor** (streamed teaching, mock interviews, answer grading). It is built on the same stack it teaches: **FastAPI (async) + SQLAlchemy 2.0 + Postgres/pgvector + JWT + Docker + an LLM API**.

## Provenance (important context)
This project was **extracted from Visakh Padmanabhan's `Resume-app`** (a resume-tailoring agent that lives at `~/Desktop/Resume-app`). The learning content was generated there:
- The **68 lessons** were authored as a static study site in `Resume-app/learning-path/` (11 modules, sourced from his job-application history and his Notion "AI Engineer Interview Question Bank").
- The **~110-question interview bank with answer keys** came from the same place.
That content is **bundled here in `content/`** (a self-contained copy of `learning-path/modules/` + `question-bank.html`) and ingested into the database on startup. This repo no longer depends on `Resume-app`; it stands alone. When updating curriculum content, edit `content/` here (or re-copy from `Resume-app/learning-path/` if regenerated there).

## The LLM tutor is provider-agnostic (users bring their own key)
Anyone running this can plug in **whatever key/provider they want** via `backend/.env`. It degrades gracefully with no key (the rest of the app works).
- **Groq** (free tier, no card): `LLM_PROVIDER=groq`, `GROQ_API_KEY=gsk_...`. Default models: `llama-3.3-70b-versatile` (tutor) / `llama-3.1-8b-instant` (judge).
- **Anthropic (Claude)**: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=sk-ant-...`. Models: Opus 4.8 (tutor) / Haiku 4.5 (judge).
- **Any OpenAI-compatible host** (OpenAI, Together, OpenRouter, local Ollama): keep `LLM_PROVIDER=groq`, set the key, and point `OPENAI_BASE_URL` at the host.
`LLM_PROVIDER=auto` picks Groq if its key is set, else Anthropic. The provider abstraction lives in `backend/app/services/ai.py`; the tutor persona/grounding is the `VISAKH_CONTEXT` / `system_for()` there.

## Run / test / deploy
```bash
./run.sh                 # local: venv + deps + seed + server on :8000 (SQLite, zero-config)
make test                # in-process smoke test (18 assertions)
docker compose up --build    # full stack: API + Postgres(pgvector) + Redis
```
Dev login (local SQLite only): **visakh@local / learn**, seeded on first start. On a Postgres deploy the seed is skipped (no shared default login), so register an account. Hosting (Render + Groq + optional Neon) is in `DEPLOY.md`; one-click via `render.yaml`. The HTML docs are in `docs/` (open `docs/index.html`).

## Project structure
```
ai-engineer-mastery/
├── backend/app/
│   ├── main.py          # app + lifespan: init db -> ingest content/ -> seed user
│   ├── config.py        # settings (DB, provider keys, content path); reads backend/.env
│   ├── database.py      # async engine; PGVECTOR_OK flag (pgvector -> JSON fallback)
│   ├── models.py        # User, Module, Lesson, Question, Progress, ReviewCard, Note, Tutor*, Attempt
│   ├── schemas.py       # Pydantic v2 contracts
│   ├── security.py      # bcrypt (sha256-prehashed) + JWT
│   ├── routers/         # auth, lessons, progress, review, tutor, analytics, notes
│   └── services/        # ai (provider-agnostic), srs (FSRS-6), ingest, activity
├── frontend/            # vanilla JS, no build step; assets/{base.css,app.css,api.js}
├── content/             # bundled lessons (modules/) + question-bank.html  <-- the curriculum
├── docs/                # styled HTML documentation (index, architecture, deploy)
├── Dockerfile  docker-compose.yml  render.yaml  run.sh  Makefile  DEPLOY.md  README.md
```

## Conventions for editing this code
- **Stack:** async everything (async SQLAlchemy, async routes, async LLM clients). Keep provider SDK imports lazy (inside the client getters in `ai.py`) so the app runs without every provider installed.
- **DB portability:** must keep running on both SQLite (default) and Postgres. The `Vector` type in `models.py` is real pgvector on Postgres-with-the-extension and JSON text otherwise (`PGVECTOR_OK`). Do not assume pgvector; do not break SQLite.
- **Content / Q&A are first-class:** `content/` holds the lessons AND the question bank **with answer keys**. `services/ingest.py` parses lessons (BeautifulSoup) and the `question-bank.html` `.q-list` items (question + `Key:` answer) into `Question` rows. Keep both; the spaced-repetition deck depends on the questions + answers.
- **Frontend:** plain HTML + `assets/api.js` (the only fetch layer) + `base.css`/`app.css`. No frameworks, no build. `escapeHtml` all dynamic text except trusted `lesson.body_html`.
- **AI grounding (when touching the tutor persona):** the tutor may reference Visakh's real work (MaiQ, the 37%/2% chunk-eval result, hybrid BM25+dense+RRF into pgvector, the MaiQ Skill Store). Never fabricate experience beyond what `VISAKH_CONTEXT` states. American English, no em-dashes in UI copy.
- **Secrets:** never commit `backend/.env` (it is gitignored). Keys go in `.env` locally or the host's env in production.
- **Security defaults (do not regress):** the public default `JWT_SECRET` is auto-replaced by a random per-process secret at startup (set a stable `JWT_SECRET` in prod for persistent sessions); the `visakh@local/learn` seed account is created **only on local SQLite**, never on a Postgres deploy with the default password (`allow_seed_user`); registration honors `ALLOW_REGISTRATION`; tutor endpoints are per-user rate-limited (`AI_RATE_PER_MIN`, `services/ratelimit.py`); CORS sends credentials only for explicit, non-`*` origins; SQLite enforces foreign keys; and `lesson_id`/`question_id` are validated (404) before writes. Provider/runtime errors are logged server-side, never echoed verbatim to clients.
- **After changes:** run `make test` (18 assertions) before committing.

## Commands cheat-sheet
| Task | Command |
|---|---|
| Run locally | `./run.sh` |
| Smoke test | `make test` |
| Full stack | `docker compose up --build` |
| Use Groq | set `GROQ_API_KEY` + `LLM_PROVIDER=groq` in `backend/.env` |
| Use Claude | set `ANTHROPIC_API_KEY` + `LLM_PROVIDER=anthropic` |
| Deploy | see `DEPLOY.md` / `render.yaml` |
