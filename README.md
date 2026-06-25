# AI Engineer Mastery

A production-shaped full-stack web app that turns a **68-lesson AI-engineering + system-design curriculum** into a real product: accounts, a database, an FSRS spaced-repetition engine, progress + streak tracking, weak-area analytics, and an **in-app AI tutor** (streamed teaching, mock interviews, answer grading) that runs on **any LLM provider you plug in** — Groq (free), Claude, or any OpenAI-compatible endpoint.

It is built deliberately on the same stack it teaches — **FastAPI (async) + SQLAlchemy 2.0 + Postgres/pgvector + JWT + Docker** — so building, running, and extending it *is* the lab for the curriculum.

```
┌────────────────────────────────────────────────────────────────────┐
│  Browser (vanilla JS, no build step)                                │
│   dashboard · lesson viewer · FSRS review · AI tutor · mock · stats  │
└───────────────┬────────────────────────────────────────────────────┘
                │  JSON / streamed text   (JWT bearer)
┌───────────────▼────────────────────────────────────────────────────┐
│  FastAPI (async)                                                     │
│   auth · curriculum · progress · review(FSRS) · tutor · analytics    │
│   services: ai (provider-agnostic) · srs (FSRS-6) · ingest           │
└───────┬───────────────────────────────┬────────────────────────────┘
        │                               │   pick one (bring your own key)
┌───────▼─────────┐            ┌────────▼───────────────────────────┐
│ Postgres+pgvector│           │  Groq (free)  ·  Claude  ·  OpenAI- │
│ (SQLite locally) │           │  compatible (Together/OpenRouter/   │
│                  │           │  Ollama via OPENAI_BASE_URL)        │
└─────────────────┘            └────────────────────────────────────┘
```

> **Provenance:** this app was extracted from Visakh Padmanabhan's resume-tailoring agent (`Resume-app`). The 68 lessons and the ~110-question interview bank were generated there and are **bundled in `content/`**; this repo stands alone.

## Quick start

### Local — zero external services (SQLite)
```bash
./run.sh                 # creates venv, installs deps, ingests content, starts on :8000
```
Open **http://localhost:8000**, sign in with **`visakh@local` / `learn`**. Everything works without an API key; add one to turn on the live tutor.

### Full stack via Docker (Postgres + pgvector + Redis)
```bash
GROQ_API_KEY=gsk_... docker compose up --build      # or ANTHROPIC_API_KEY=sk-ant-...
```

### Turn on the AI tutor — bring your own key, any provider
Edit `backend/.env` (created on first run) and set **one** provider:
```bash
# Groq — FREE, no credit card (https://console.groq.com)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
# …or Claude:        LLM_PROVIDER=anthropic   ANTHROPIC_API_KEY=sk-ant-...
# …or any OpenAI-compatible host: keep groq, set the key, and set OPENAI_BASE_URL
```
`LLM_PROVIDER=auto` auto-detects. Groq uses `llama-3.3-70b-versatile` (tutor) / `llama-3.1-8b-instant` (judge); Claude uses Opus 4.8 / Haiku 4.5 — the same cost-aware tutor/judge split either way.

## Features

| Area | What it does |
|---|---|
| **Curriculum** | All 68 lessons ingested into the DB and rendered in-app with progress + streak tracking. |
| **Spaced repetition** | The ~110-question bank (questions **and** answer keys) scheduled with **FSRS-6** (2026 state of the art, ~30% fewer reviews than SM-2). Daily review queue, 4-button grading, per-card state. |
| **AI tutor** | Streamed Socratic teaching ("deepen"), realistic **mock interviews** (one question at a time, escalating, scored), and structured **answer grading** (score + the one highest-leverage fix + a model answer). Pulls your notes in as context. |
| **Active recall** | On any review card, type your answer first and have the AI grade it before you reveal the key. |
| **Analytics** | Weak-area detection from graded attempts, strongest topics, a 30-day activity heatmap, streaks. |
| **Notes** | Per-lesson notes that become tutor context. |
| **Auth** | JWT, bcrypt (sha256-prehashed), seeded dev account. |

## Project structure
```
ai-engineer-mastery/
├── backend/app/
│   ├── main.py          # app + lifespan: init db -> ingest content/ -> seed user
│   ├── config.py        # settings (DB, provider keys, content path)
│   ├── database.py      # async engine; pgvector with JSON fallback (any Postgres)
│   ├── models.py        # User, Module, Lesson, Question, Progress, ReviewCard, Note, Tutor*, Attempt
│   ├── security.py      # bcrypt + JWT
│   ├── routers/         # auth, lessons, progress, review, tutor, analytics, notes
│   └── services/        # ai (provider-agnostic), srs (FSRS-6), ingest, activity
│   └── check.py         # in-process smoke test (28 assertions)
├── frontend/            # vanilla JS; index/login/lesson/review/tutor/mock/analytics + assets/
├── content/             # bundled curriculum: lessons (modules/) + question-bank.html (Q + answers)
├── docs/                # styled HTML documentation (open docs/index.html)
├── Dockerfile  docker-compose.yml  render.yaml  run.sh  Makefile  DEPLOY.md  CLAUDE.md
```

## API (selected)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | JWT auth |
| GET | `/api/curriculum` · `/api/lessons/{day}` | content + completion |
| POST | `/api/progress` | mark complete, update streak |
| GET | `/api/review/queue` · POST `/api/review/grade` | FSRS review loop |
| POST | `/api/tutor/chat` | **streamed** tutor / deepen / mock |
| POST | `/api/tutor/grade` | structured answer grading |
| GET | `/api/analytics` · `/api/meta` | weak areas + streaks · counts/provider/SRS |

Interactive OpenAPI docs at **`/docs`** while the server runs.

## Test
```bash
make test          # boots the app in-process and runs 28 assertions
```

## Deploy (free)
**Render + Groq + (optional) Neon** = $0. One-click via `render.yaml`, full guide in **`DEPLOY.md`**. The app is self-contained (content baked in), honors `$PORT`, normalizes host `postgres://` URLs, and falls back to JSON embeddings on any Postgres without pgvector.

## Roadmap
- Embeddings (Sentence-Transformers) to light up pgvector semantic search + RAG-over-your-notes.
- Redis prompt/semantic cache + per-user rate limiting.
- Request tracing (token/cost) + an eval-the-grader harness.
- Alembic migrations; optional Next.js frontend.

---
Built by Visakh Padmanabhan. Curriculum and question bank originated in `Resume-app/learning-path`, bundled here in `content/`.
