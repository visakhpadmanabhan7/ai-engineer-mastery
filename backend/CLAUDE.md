# CLAUDE.md — backend/

The FastAPI backend. Async throughout. See the repo-root `CLAUDE.md` for the big picture.

## Layout
```
app/
  main.py        # FastAPI app + lifespan: init_db -> ingest content/ -> seed user; mounts frontend/
  config.py      # pydantic-settings; reads backend/.env; provider + DB + content config
  database.py    # async engine/session; Base; PGVECTOR_OK flag; init_db()
  models.py      # SQLAlchemy 2.0 models + the portable Vector type
  schemas.py     # Pydantic v2 request/response contracts
  security.py    # bcrypt (sha256-prehash) + JWT
  deps.py        # get_current_user (OAuth2 bearer)
  routers/       # auth, lessons, progress, review, tutor, analytics, notes
  services/      # ai (provider-agnostic), srs (FSRS-6), ingest, activity
check.py         # in-process smoke test (16 assertions)
```

## Run / test
```bash
../run.sh                              # from repo root: venv + deps + server
PYTHONPATH=. .venv/bin/python check.py # smoke test (or `make test` from root)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

## How to extend
- **Add a router:** create `routers/x.py` with an `APIRouter(prefix="/api/x")`, then add it to the `for r in (...)` include loop in `main.py`.
- **Add a model:** add it to `models.py`; tables are created via `Base.metadata.create_all` on startup (no Alembic yet — for a schema change in dev, delete `backend/learning.db` to recreate).
- **Add a tutor capability:** edit `services/ai.py`. Keep provider SDK imports **lazy** (inside `_anthropic()` / `_openai()`), branch on `provider()`, and keep streaming (`stream_chat`) and structured (`grade`) paths working for both backends.

## Rules
- **Async everywhere.** Don't block the event loop; never `await` an LLM call inside a DB transaction.
- **Both DBs must work:** SQLite (default) and Postgres. Don't assume pgvector — the `Vector` type degrades to JSON via `PGVECTOR_OK`. Don't hardcode Postgres-only SQL.
- **Streaming persistence gotcha:** the tutor stream generator opens a **fresh** `SessionLocal()` to save the assistant message, because the request-scoped session is closing when the stream runs. Keep that pattern.
- **Secrets:** keys live in `backend/.env` (gitignored). Never commit `.env`. Validate before any push.
- Run `check.py` before committing.
