# Architecture and Prioritization

## Product decision

Deliver a credible, end-to-end document lifecycle rather than approximate every feature in Google Docs: **create → edit/format → save/reopen → upload → share → verify access**. The application is intentionally optimized for a reviewer to complete that workflow in minutes.

## Stack

- **Frontend:** semantic HTML, responsive CSS, vanilla JavaScript, browser-native `contenteditable`, and simple formatting controls. Avoids a JS compilation/build chain. Edits are debounced with clear saving feedback.
- **Backend:** Python standard-library threaded HTTP server. Explicit routes, JSON and multipart validation, server-side authorization, basic signed session cookies, and CSRF checks.
- **Storage:** SQLite by default for frictionless local use. PostgreSQL for Render via `DATABASE_URL`; `psycopg2-binary` is only needed for deployment with Postgres.
- **Deployment:** Render Blueprint with a Python web service and PostgreSQL datastore. Keep the database separate from an ephemeral web-service filesystem.

## Data model

`users(id, name, email)` — three seeded demo personas.

`documents(id, owner_id, title, content, revision, created_at, updated_at)` — sanitized HTML content and revision for optimistic concurrency.

`shares(document_id, user_id, role)` — unique user/document pair, `view` or `edit`. Owner is derived from the document; owners do not need a share row.

## Access control

Reads require ownership or a share row. Writes require owner or editor; sharing modifications require the owner. View-only users are blocked both in the UI and on the server. Server checks are authoritative. Demo account switching is *not real authentication*, so this is suitable for a technical assessment only.

## Consistency

The frontend saves after ~700 ms of editing inactivity. Each PATCH submits a `revision`, and the server updates only if the stored revision matches. Conflicting edits receive HTTP 409 instead of overwriting data silently. This is a minimal conflict-detection measure, **not real-time collaborative editing**. On a conflict the UI stops autosaving, warns the user to copy visible changes before reloading, and avoids losing their typing silently.

## Trust boundary and validation

The server sanitizes rich text to a narrow safe HTML set, strips attributes and executable elements, rejects invalid titles, checks request sizes, restricts imports to UTF-8 `.txt` under 1 MB, and returns structured errors. Signed demo cookies plus CSRF reduce accidental cross-site mutations; production would require real identity and additional hardening (rate limits, secret rotation, security reviews, lifecycle policies).

## Scope tradeoffs

1. **Rich text over broad file formats.** `.txt` import satisfies the upload workflow without fragile `.docx` parsing.
2. **Seeded users over login flows.** Reviewers can verify both sides of sharing without password, email, or external identity dependencies.
3. **Reliable async save over real-time cursors.** Autosave, clear status, and conflict detection are more demonstrable in a short build.
4. **Minimal dependencies over framework sprawl.** A Python service and server-rendered static frontend remove bundler/database migration complexity.
5. **Postgres for cloud durability.** SQLite remains simplest locally; hosting uses managed storage rather than the ephemeral service disk.

## Next 2–4 hours

Add properly authenticated user accounts, test actual simultaneous editing sessions in multiple browsers, implement a server-side transaction around document updates for stronger concurrency guarantees, introduce structured document operations (e.g. a rich-text editor library), add browser-level UI tests and accessibility audits. Consider version history after core reliability is proven.

## Known limitations

- `document.execCommand` is a legacy browser formatting API. It is intentionally used to avoid the dependency and initialization overhead of a full editing framework in this assessment. Verify formatting in the target review browser; a production version would use an actively maintained editor.
- The SQLite local path is persistent across refresh/restart **as long as the file is retained**. The free Render application filesystem is not durable across deployments, hence the supplied Postgres configuration.
- Two editors of the same document cannot merge concurrent changes automatically. Conflicts are detected; users must resolve manually.
- The document PATCH checks the expected revision against the retrieved document and the UPDATE predicate. This prevents stale overwrites but leaves room for stronger transactional semantics on high contention.
- End-to-end browser visual and deployment checks must be completed on the live environment before describing the UI or live service as verified.
