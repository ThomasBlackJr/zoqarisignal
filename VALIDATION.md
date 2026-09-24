# Validation record

Verified locally on Windows using Python 3.12 and Node.js 24.

| Check | Result |
| --- | --- |
| Backend pytest | 80 passed after the speaker-turn update, including all QA regressions |
| Backend Ruff | Passed |
| Alembic upgrade | Initial migration applied successfully |
| Alembic model drift check | No new upgrade operations detected |
| Frontend ESLint | Passed |
| TypeScript | Passed |
| Next.js production build | Passed; all application routes built |
| Playwright / installed Chrome | 2 tests passed: full workflow and grouped transcript UI |
| Desktop and mobile screenshots | Inspected; narrow-screen overflow corrected |
| PowerShell launcher parsing | Both scripts passed |

The browser run started real Next.js and FastAPI processes with an isolated temporary database. It signed in, uploaded a valid WAV, waited for processing, played the original audio, checked the stored transcript and all six category scores, reloaded the page, searched the library, checked the dashboard, verified the mobile layout, logged out on mobile, and confirmed protected navigation returned to login. No browser page errors occurred.

The backend suite additionally covers denied access, role enforcement, CSRF, hashed/expiring/revoked sessions, login throttling, invalid and oversized uploads, range playback, provider substitution and timestamp preservation, transcription and QA failures, safe database errors, validation without password disclosure, structured response refusals, score/evidence validation, retries, and restart recovery.

Speaker-turn tests cover known/inferred grouping, identity and role boundaries, UNKNOWN handling, timestamp correctness, exact text/whitespace preservation, raw-data immutability, source alignment fallback, cache version/source validation, local formatting of existing calls without provider requests, independent formatting failures, and a legacy-schema upgrade/downgrade. Migration `b192cb82ae01` was applied to the local database with before/after equality checks confirming the two raw transcripts and existing QA result were unchanged. No live provider requests were made for this update. See `TRANSCRIPT-UPDATE.md`.

Two dependency deprecation warnings remain in the Starlette/httpx test client integration; they do not fail the tests. During the subsequent QA investigation, a live QA-only request through the revised adapter passed strict validation using the saved transcript. No transcription request was made by that investigation and the existing call/transcript were not modified. See `QA-FIX.md` for the reproduced failure and regression tests. PostgreSQL was not available for an integration run; SQLite was used. The first-account interactive launcher was syntax-checked; its underlying migration, CLI dependencies, server entry point, and application workflow were exercised separately.
