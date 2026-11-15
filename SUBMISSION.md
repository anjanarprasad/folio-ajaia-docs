# Ajaia AI-Native Full Stack Developer — Submission

**Candidate:** Anjana Rajendra Prasad

**Application:** Folio — Lightweight Collaborative Document Editor

## Included artifacts

- `server.py` — Python HTTP/API backend, SQLite/PostgreSQL storage, validation and permissions
- `static/index.html` — document dashboard and editing UI
- `static/app.css` — responsive styling
- `static/app.js` — editing, autosave, sharing, file import and API client
- `tests/test_app.py` — six automated end-to-end HTTP tests
- `requirements.txt` — optional PostgreSQL driver
- `render.yaml` — Render Blueprint for web service + PostgreSQL
- `README.md` — local setup, tests, deployment and usage
- `ARCHITECTURE.md` — design, priorities and tradeoffs
- `AI_WORKFLOW.md` — AI collaboration, corrections and verification
- `VIDEO_LINK.txt` — walkthrough video URL placeholder
- `WALKTHROUGH_SCRIPT.md` — suggested 3–5 minute narration
- `.gitignore` — local and secret artifacts excluded

## Links (fill these before submitting)

**Live app URL:** NOT YET DEPLOYED — paste the tested Render URL

**Walkthrough video URL:** NOT YET RECORDED — paste the unlisted Loom/YouTube URL

**Google Drive folder URL:** https://drive.google.com/drive/folders/1xPHxcgoDZsnvSrC40ReYnmd8-1L4PRUk (created; source ZIP must still be uploaded and reviewer access enabled)

## Reviewer flow

1. Open the live product URL (or run `python server.py` locally).
2. As **Anjana Prasad**, create and rename a document; type and format text; wait for the save status; refresh/reopen.
3. Import a UTF-8 `.txt` file through **Import .txt**.
4. Share a document with **Alex Morgan** (`alex@example.com`, Can edit) and **Priya Shah** (`priya@example.com`, Can view).
5. Switch demo accounts using the bottom-left selector. Confirm Alex can edit, Priya can view, and documents distinguish **Owned by me** from **Shared with me**.
6. Run `python -m unittest discover -s tests -v` for six backend tests.

## Working / partial / future

**Working locally:** create, rename, format, save, reopen, `.txt` import, mocked sharing, access controls, local SQLite persistence, API tests.

**Not yet independently verified:** public deployment, cross-browser UX, recorded walkthrough.

**Deliberately omitted:** real sign-in, collaborative cursors, `.docx` import, comments, PDF export, rich revision history.

**With another 2–4 hours:** add real login and browser-driven UI tests, strengthen concurrency with transactional updates, improve keyboard/accessibility support, and add a structured rich-text editing library.

## Demo credentials

No passwords: select **Anjana Prasad**, **Alex Morgan**, or **Priya Shah** in the sidebar. Demo account switching is deliberately unauthenticated and should not be treated as production user management.
