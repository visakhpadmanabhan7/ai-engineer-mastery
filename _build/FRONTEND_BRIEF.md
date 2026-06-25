# FRONTEND BRIEF — AI Engineer Mastery web app pages

You are building ONE static HTML page (vanilla JS, no framework, no build step) for a learning web app. It must match the existing pages exactly in conventions and styling.

## STEP 0 — read these first
- `/Users/visakh/Desktop/Resume-app/learning-app/frontend/index.html` — the canonical exemplar (dashboard). Copy its structure, the `<head>` (loads `assets/base.css` + `assets/app.css`), the trailing `<script src="assets/api.js"></script>` + inline `<script>`, the `requireAuth()` / `renderNav()` boot, `escapeHtml`/`toast` usage, error handling.
- `/Users/visakh/Desktop/Resume-app/learning-app/frontend/assets/api.js` — the API client. Use ONLY these global functions; do not write your own fetch.
- `/Users/visakh/Desktop/Resume-app/learning-app/frontend/assets/app.css` and `assets/base.css` — use ONLY classes defined there (listed below). Do not add `<style>` blocks except tiny one-off inline `style=""` tweaks.

## PAGE BOOT (every page)
```html
<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title><PAGE> — AI Engineer Mastery</title>
<link rel="stylesheet" href="assets/base.css"><link rel="stylesheet" href="assets/app.css">
</head><body>
<div class="wrap" id="app"><div class="muted-center" id="loading"><span class="spinner"></span> Loading…</div></div>
<script src="assets/api.js"></script>
<script>
if (!requireAuth()) { /* redirected to login */ }
renderNav("<NAV_ID>");   // dash | review | tutor | mock | analytics
// ... page logic, async load() with try/catch, escapeHtml all dynamic text
</script></body></html>
```

## API CONTRACT (global functions from api.js; all async unless noted)
- `me()` → `{id,email,display_name,current_streak,longest_streak,daily_goal_lessons}`
- `getCurriculum()` → `[{id,slug,number,title,week,is_core, lessons:[{id,day,slug,title,est_minutes,difficulty,module_id,completed}]}]`
- `getProgress()` → `{completed_days:[int], total:int, pct:float, current_streak:int}`
- `setProgress(lesson_id, completed=true, secs=0)` → progress payload
- `getLesson(day)` → `{id,day,slug,title,est_minutes,difficulty,module_id,body_html,summary}` — **body_html is trusted lesson HTML using base.css classes; render with `innerHTML` (do NOT escape it).**
- `getReviewQueue(limit=20)` → `{items:[{question:{id,topic,prompt,answer_key,difficulty}, due, state, reps}], engine}`
- `gradeCard(question_id, rating)` → `{ok,due,state,reps}` — rating: **1=Again 2=Hard 3=Good 4=Easy**
- `getReviewStats()` → `{due_now,new_available,reviewed_today,total_cards}`
- `tutorStream(body, onChunk)` → returns session id string. `body = {kind, message, lesson_id?, session_id?, module_id?}`, kind ∈ `chat|deepen|mock`. Calls `onChunk(textChunk)` repeatedly as the reply streams. Append chunks to the current assistant bubble.
- `tutorGrade(question, user_answer, {kind?, lesson_id?})` → `{score,feedback,model_answer,one_fix}` (score is 0–10 number)
- `tutorStatus()` → `{ai_enabled:bool}`
- `getTutorSessions()` → `[{id,kind,title,lesson_id,created_at}]`
- `getNotes(lesson_id?)` → `[{id,content,lesson_id,created_at}]`
- `createNote(content, lesson_id=null)` → note
- `getAnalytics()` → `{lessons_completed,lessons_total,cards_due,reviews_total,attempts_total,current_streak,longest_streak,avg_score(0-10|null),weakest_topics:[{topic,avg_score,attempts}],strongest_topics:[...],activity:{ "YYYY-MM-DD":count }}`
- helpers: `escapeHtml(s)`, `qs(key)` (read URL query param), `toast(msg)`, `logout()`

## CSS CLASSES AVAILABLE (use these, invent none)
base.css: `wrap`,`wrap-wide`,`panel`,`grid cols-2/cols-3`,`callout [concept|example|practice|interview|connect|warning|key]`,`prose`,`diagram`,`pill [gold|teal|violet|green]`,`btn [primary|ghost]`,`q-list`,`objectives`,`meta-row`,`section-rule`,`hero`,`eyebrow`,`lede`,`module`,`days`,`day [done]`,`progress-track`,`progress-fill`,`progress-label`,`foot`,`muted`,`center`,`lesson-nav`,`complete-bar`,`details.solution`.
app.css: `flash`,`flash-card`,`flash-topic`,`flash-q`,`flash-a` (`.lab`),`rate-row`,`rate [again|hard|good|easy]` (with `<small>`),`review-progress`,`mode-tabs`(buttons, `.active`),`chat-log`,`msg [user|assistant]`(`.who`),`composer`(textarea+btn),`ai-off`,`grade`(`.score`,`.score small`),`bars`,`bar-row`(`.name`,`.val`),`bar-track`,`bar-fill`,`heat`,`heat-cell [l1|l2|l3|l4]`,`lesson-actions`,`note-box`,`note-item`,`stat-grid`,`stat`(`.num [.gold]`,`.label`),`today`(`.big`),`toast`,`spinner`,`muted-center`.

## CONVENTIONS
- Vanilla JS only, inline in the page's `<script>`. `async function load(){ try{...}catch(e){ document.getElementById('app').innerHTML = 'Could not load: '+escapeHtml(e.message); } }` then `load();`.
- `escapeHtml()` ALL dynamic text you inject, EXCEPT `lesson.body_html` (render raw).
- Errors: `toast(e.message)`; never leave the user staring at a spinner.
- Keep it clean, fast, and consistent with index.html. No external libraries, no fonts, no images.
- American English; no em-dashes in UI copy.

## RETURN
After writing your single file, return only the file path + a 1-line note. Do not paste file contents.
