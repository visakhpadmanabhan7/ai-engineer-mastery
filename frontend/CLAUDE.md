# CLAUDE.md — frontend/

Vanilla JS, **no build step, no framework, no libraries**. Plain HTML pages served by FastAPI as static files. See root `CLAUDE.md` for the big picture.

## Files
```
index.html      # dashboard (the exemplar to copy for new pages)
login.html      # JWT auth (login + register)
lesson.html     # lesson viewer: body_html + mark-complete + notes + deepen-tutor
review.html     # FSRS flashcards + optional AI grading
tutor.html      # streamed AI chat (chat/deepen modes)
mock.html       # scored mock interview
analytics.html  # weak-area bars + 30-day heatmap
assets/
  api.js        # THE ONLY fetch layer — all API calls go through its global functions
  base.css      # the design system (tokens + components); shared with docs/ and the lessons
  app.css       # app-specific components (nav, login, flashcard, chat, charts)
```

## The contract
- All network calls use the global helpers in `api.js` (`login`, `getCurriculum`, `getReviewQueue`, `gradeCard`, `tutorStream`, `tutorGrade`, `getAnalytics`, `createNote`, …) plus `renderNav`, `requireAuth`, `escapeHtml`, `qs`, `toast`. Do **not** write raw `fetch`.
- `tutorStream(body, onChunk)` streams the tutor reply chunk-by-chunk and returns the session id; append chunks to the current assistant bubble.

## To add a page
1. Copy the boot pattern from `index.html`: load `assets/base.css` + `assets/app.css`, then `assets/api.js`; start the script with `if (!requireAuth()) {}` and `renderNav("<id>")`.
2. Use ONLY classes defined in `base.css` / `app.css` (no new `<style>` blocks beyond tiny inline tweaks).
3. `escapeHtml()` all dynamic text **except** `lesson.body_html` (trusted lesson HTML, render raw).
4. Wrap loads in `try/catch`; surface errors with `toast()` — never leave a spinner stranded.
