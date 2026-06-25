# CLAUDE.md — content/

The bundled curriculum. This is the **source of truth for what the app teaches and quizzes**.

```
content/
  modules/                # 68 lesson HTML files across 11 module folders (m01-... .. m11-...)
  question-bank.html      # ~110 interview questions WITH answer keys (the spaced-repetition deck)
```

## Provenance
Copied from `Resume-app/learning-path/` (the static study site where this content was authored). If the curriculum is regenerated there, re-copy `modules/` and `question-bank.html` here. The app does not depend on `Resume-app`; this folder is self-contained.

## How the app uses it
`backend/app/services/ingest.py` runs on startup and:
- Parses each `modules/**/dNN-*.html` (BeautifulSoup) into a `Lesson` row: day, title, est-minutes, difficulty, and the inner content HTML (the topbar/nav/footer are stripped; the app renders its own).
- Parses `question-bank.html`'s `<ul class="q-list">` items into `Question` rows: the question text + the `Key:` line as the `answer_key`. Topic = the section `<h2 id="...">`.

Lessons **upsert by day** (edit and restart to refresh). Questions **seed once** (only when the table is empty) — to re-seed after editing, delete `backend/learning.db` (dev) or clear the `questions` table.

## Rules
- **Keep both questions AND answer keys.** The review deck and the active-recall grading depend on the `Key:` answers in `question-bank.html`. Do not strip them.
- Keep the lesson HTML structure intact (`meta-row`, `h1`, `p.lede`, `q-list`, callouts) — the ingest parser reads those, and the app renders the body with the same CSS classes (`frontend/assets/base.css`).
- Lesson days are `d01`..`d68` and must stay unique (one `Lesson` per day).
