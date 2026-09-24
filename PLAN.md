# DRIVE implementation plan

## Architecture, decided before implementation

- `frontend/`: Next.js App Router, TypeScript, responsive operations UI. A same-origin `/api` proxy connects the browser to FastAPI. HttpOnly session cookies never enter JavaScript.
- `backend/app/`: FastAPI routes, SQLAlchemy models, Pydantic contracts, session authentication, and separate transcription / QA service protocols and adapters.
- `backend/app/services/rubric.py`: the single versioned source of grading criteria. Validate category identity, maximums, totals, and quoted evidence before persistence.
- PostgreSQL for deployment; SQLite for single-machine development. Alembic owns schema changes. Audio resides in a private configurable filesystem directory and is served only after authentication.
- A single backend worker polls persisted queued calls. Transcription commits independently of QA; failures remain visible and retryable. Interrupted work becomes failed at restart. This MVP runs one backend process; distributed workers are a future operational change.
- ADMIN can create users; ADMIN and SUPERVISOR can review the shared operations call library. Database-backed, hashed opaque sessions support immediate logout/revocation, expiry, role checks, and CSRF protection through strict same-site cookies plus origin checks.
- Explicit demo adapters enable offline verification, labeled as synthetic. OpenAI adapters enable real audio transcription and structured QA without changing application routes.

## Build sequence

1. Scaffold configuration, database models, initial migration, authentication, and user bootstrap CLI.
2. Implement streaming bounded upload validation, private audio delivery, service adapters, processing worker, retries, and dashboard/library/detail APIs.
3. Build login, dashboard, call library, upload, and detail views with real API state, accessible forms, loading/error/empty states, and processing polling.
4. Test authentication/authorization, file content and limits, adapter injection, structured QA validation, failures/retries, persistence, audio, and core endpoints.
5. Run backend tests/lint, frontend lint/typecheck/production build, launch both servers, and exercise the workflow. Document installation, configuration, limits, and external service requirements.

## Deliberate MVP limits

No future analytics, diarization, notifications, SSO, or advanced RBAC. No automatic retry that could silently repeat API charges. AI results require human review. Local demo mode never claims to transcribe the uploaded audio.
