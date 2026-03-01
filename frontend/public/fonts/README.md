Self-hosted fonts used by the project.

Sans family:
- Inter

Mono family:
- JetBrains Mono

Expected files in `frontend/public/fonts/`:
- `Inter-Regular.woff2`
- `Inter-Bold.woff2`
- `JetBrainsMono-Regular.woff2`
- `JetBrainsMono-Bold.woff2`

Notes:
- `frontend/src/app/globals.css` defines `@font-face` with `font-weight` 400 and 700.
- `globals.css` also declares `unicode-range` for `latin` and `latin-ext`.
- If you change files or font families, update `globals.css` accordingly.
