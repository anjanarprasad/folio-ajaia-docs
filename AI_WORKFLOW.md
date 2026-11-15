# AI-Native Workflow Note

## Tools used

- **ChatGPT (GPT-6):** translated the product prompt into an MVP scope, designed the data model and API, drafted frontend/backend implementation, and generated test cases and documentation.
- **Python standard-library `unittest`:** ran six actual HTTP tests against the application.
- **Node syntax check:** used `node --check` to check client-side JavaScript syntax in the working environment.

## Where AI materially helped

AI accelerated implementation across the full stack: decomposed requirements into a demonstrable document lifecycle; generated HTML, CSS, JS, the Python storage layer and routes; identified owner/editor/viewer permissions; suggested stale-write protection and sanitization; and wrote automated tests. It also made it practical to produce coherent README and architecture documentation within the timebox.

## Changes, rejections, and judgment

- A Python framework approach originally considered for the app required packages that could not be downloaded in the coding environment. That dependency-heavy option was discarded in favor of the standard library, allowing local runtime and tests without network installation.
- A first implementation of the HTTP handler accidentally reused the base class's `handle` method name. It was corrected to `handle_request` before validation. This demonstrates why generated code was inspected and tested instead of accepted blindly.
- Rich-text formatting was limited to a practical set, and `.docx` import, full authentication, and live cursors were intentionally deferred.
- Kept **server-side** authorization and HTML sanitization; disabling controls in the browser alone would not enforce permissions.
- Chose managed PostgreSQL for deployment instead of pretending an ephemeral Render SQLite file was durable.

## Verification performed

**Completed:** Python compilation; JavaScript syntax validation; six HTTP/API tests covering document creation, formatting persistence, document reopening, sharing rights, unauthorized access, stale edits, import, XSS stripping, and CSRF validation.

**Pending until manually performed:** browser UI walkthrough, Render live-deployment smoke test, real multi-account review in the hosted app, and the 3–5 minute recorded video. Do not claim these have been completed until verified.

## Reflection

The value of AI here was not generating maximal code. The leverage came from selecting a testable product slice, cutting scope, surfacing risks, correcting mistakes, validating core workflows, and clearly documenting what remains incomplete.
