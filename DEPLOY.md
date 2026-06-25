# Deploying (free)

The recommended free stack: **Render** (app) + **Groq** (LLM, free tier, no card) + Render's free **Postgres** (or **Neon** for a long-lived DB with pgvector). Total cost: $0.

The app is self-contained and deploy-ready: the 68 lessons are baked into the image, it honors `$PORT`, it converts host `postgres://` URLs for asyncpg automatically, and it falls back to JSON embeddings if a host's Postgres lacks pgvector. No code changes needed to ship.

---

## Step 1 — get a free Groq key
<https://console.groq.com> -> API Keys -> Create. No credit card. Free tier is ~30 requests/min, which is plenty for one learner.

## Step 2 — deploy the app on Render

### Option A: one-click Blueprint (easiest)
1. Push the `learning-app/` folder to its own GitHub repo.
2. Render dashboard -> **New -> Blueprint** -> select the repo. It reads `render.yaml` and provisions the web service **and** a free Postgres.
3. When prompted, paste your `GROQ_API_KEY`.
4. Open the URL Render assigns and click **Register** to create your account. (The demo seed account is intentionally not created on the hosted Postgres database, so there is no shared default login.)

### Option B: manual web service
1. Render -> **New -> Web Service** -> connect the repo -> **Runtime: Docker**.
2. Add environment variables:
   - `LLM_PROVIDER=groq`
   - `GROQ_API_KEY=gsk_...`
   - `JWT_SECRET=` (any 32+ char random string)
   - `DATABASE_URL=` (from your database, see Step 3)
3. Deploy.

> The free web service **sleeps after 15 min idle** (first request after that takes ~1 min to wake). That is normal for free hosting.

## Step 3 — the database

- **Render Postgres (free):** provisioned automatically by the Blueprint. Easiest. Note the free instance expires ~30 days after creation; recreate or upgrade when it does.
- **Neon (free, persistent, has pgvector) — recommended for longevity:** create a project at <https://neon.tech>, copy the connection string, and set on Render:
  - `DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST/dbname`
  - `PG_SSL=true`
  Neon supports pgvector, so semantic features light up once you add embeddings (README roadmap).

> SQLite is **not** suitable on Render (the disk is ephemeral and resets on deploy/sleep) — use Postgres in production.

## Step 4 — verify
Open `/api/meta` on your deployed URL. You should see your lesson/question counts, `"srs_engine":"FSRS-6"`, and `"ai": {"provider":"groq", ...}`. Then sign in and try the AI Tutor.

---

## Alternatives

- **Fly.io** (now needs a card, but generous): `flyctl launch` (detects the Dockerfile) -> `fly secrets set GROQ_API_KEY=... LLM_PROVIDER=groq JWT_SECRET=...` -> attach Postgres with `fly postgres create` and `fly postgres attach` -> `fly deploy`. Run interactive login first with `! flyctl auth login`.
- **Railway / Northflank:** similar Docker + Postgres flow; set the same env vars.
- **Local production stack:** `GROQ_API_KEY=gsk_... docker compose up --build` runs the API + Postgres(pgvector) + Redis on your machine.

## Switching the LLM provider
The tutor is provider-agnostic. Set `LLM_PROVIDER` and the matching key:
- `groq` + `GROQ_API_KEY` (free) — default for hosting.
- `anthropic` + `ANTHROPIC_API_KEY` — Claude (Opus 4.8 tutor, Haiku judge).
- Any other OpenAI-compatible host (OpenAI, Together, OpenRouter, a local Ollama): keep `LLM_PROVIDER=groq`, set `GROQ_API_KEY` to that host's key, and point `OPENAI_BASE_URL` at it.
