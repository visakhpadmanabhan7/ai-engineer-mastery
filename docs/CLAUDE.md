# CLAUDE.md — docs/

Static, styled HTML documentation for the app. Self-contained (no server needed); can be published to GitHub Pages.

```
index.html          # overview / showcase (the exemplar)
architecture.html   # stack, data model, AI provider abstraction, FSRS, DB portability
deploy.html         # the free hosting guide (Render + Groq + Neon), rendered from DEPLOY.md
assets/style.css    # a copy of the app's design system (frontend/assets/base.css)
```

## To add or edit a doc page
- Copy `index.html`'s `<head>` and `.topbar` nav; load `assets/style.css`; set the active nav link.
- Use ONLY the CSS classes in `assets/style.css` (wrap, wrap-wide, hero, eyebrow, lede, panel, grid, callout, diagram, pill, btn, table, pre/code with `.tok-*` spans, foot, section-rule). No external libraries, fonts, or images.
- American English, no em-dashes in prose. Keep it cohesive with `index.html`.
- If the app's design system changes, refresh `assets/style.css` from `../frontend/assets/base.css`.
