# Zoqari Signal

**Quality intelligence for every interaction.**

Signal evolves the working DRIVE application into an organization-isolated quality review product. Day 2 Part 1 supplies customer entry and access gating. **Day 2 Part 2** adds durable bulk uploads, tracked employees and audited assignment, corrected-transcript reevaluation, current performance summaries, team invitations, per-user dashboards and Light/Dark/System appearance. See `DAY2-PART2-PLAN.md` and the current `SIGNAL-HANDOFF.md` for exact delivery boundaries. Real billing and public deployment remain future work.

The organizational hierarchy milestone adds real Employee reporting relationships, audited manager changes, manager/team performance pages, server-side manager filters and optional explicit User links. Managers need no login. Team scores use current direct reports and interaction-weighted eligible evaluations. Manager-role access is unchanged; see `SIGNAL-HANDOFF.md` for the complete model, migration and limitations.

The product-control milestone adds explicit **Can manage employees** designation, published Scorecard selection for single/bulk upload and new QA evaluations, and Owner/Admin call deletion plus employee archive/safe permanent deletion. Corrected-transcript reevaluation still pins its previous scorecard. See the latest handoff for deletion recovery and migration semantics.

## Working features

- Bulk manifests with independent file validation/progress, persisted server processing, individual retries and same-organization exact-byte duplicate linking (up to 100 files).
- Tracked employees distinct from login users, audited assign/reassign/unassign, search/filter, deactivation without deletion, and current version-aware category summaries.
- Corrected speaker revisions mark older QA outdated; explicit reevaluation pins published rubric/context and reuses saved transcription. Current aggregates exclude outdated/history and reflect current employee assignment.
- Owner/Admin team invitations with secure expiring one-use tokens and existing-account authentication. Local delivery is explicitly development-only.
- Server-persisted per-user module visibility/order and Light/Dark/System appearance.

- Register and verify an account, create a business as Owner, and manage basic account access. Existing ADMIN/SUPERVISOR accounts remain compatible. All operational reads and mutations require verified membership and an active entitlement and are scoped to the signed-in organization.
- Expiring single-use email verification/password recovery, explicit local development mail outbox or TLS SMTP delivery, and session revocation on reset. Development-only seven-day access activation; no real checkout or payment is claimed.
- Upload WAV, MP3, or M4A audio; asynchronous persisted queue, private authenticated playback, search, status/review filters, sorting, and pagination.
- Existing OpenAI transcription and QA adapters; explicit, visibly synthetic demo mode for offline development.
- Immutable raw text and segments, lossless conversational turns, conservative speaker inference, timestamp seeking, raw view, and audited role corrections. Bulk corrections only apply to an actual shared provider speaker ID.
- Organization-specific, normalized, versioned scorecards (internally called rubrics). Admins create/duplicate/edit/reorder drafts and publish only when weights total exactly 100. Multiple versions may remain published; archive explicitly to remove a version from new selections. Supervisors can view but cannot change scorecards.
- A prominent **Signal Score** (effective final total) beside the unchanged AI score. Category adjustments require a reason, remain within the historical category maximum, and append actor/time/previous-score history. Reset appends a record and restores the AI value.
- Complete-review action and actionable review queue. Dashboard averages use latest final scores; historical evaluations do not inflate metrics.
- Explicit new QA evaluations use saved transcripts, retain earlier results and their adjustments, and capture the requested scorecard. Failed QA retries also reuse saved transcription.
- Verified Zoqari raster assets, self-hosted Sora/Inter, compact blue/Midnight interface, responsive navigation/forms, keyboard dialogs, and reduced-motion support.

## Start or restart locally (Windows)

The working directory remains named `DRIVE` to preserve existing paths and data. Stop existing application services with Ctrl+C before restarting.

```powershell
Set-Location 'C:\Users\Thoma\Documents\Codex\2026-09-18\files-pasted-by-the-user-i\outputs\DRIVE'
.\Setup-Signal.ps1
.\Start-Signal.ps1
```

Setup installs Python and frontend dependencies and only copies environment examples if the destination does not exist. It does not overwrite your configured key. Start checks ports 3000/8000, runs Alembic migrations, then starts the backend and frontend. Create new accounts in the browser. Existing credentials continue working; after migration an Owner/Admin must activate development access once on the account screen. Open `http://localhost:3000`. The compatibility commands `Setup-Drive.ps1` and `Start-Drive.ps1` still work.

This local project's environment now enables development activation and local mail. With MAIL_DELIVERY=local, no email is sent: open the verification/reset link in the newest private `backend/data/mail-outbox` message. A fresh source checkout should copy `.env.example`; existing installations must explicitly add ENVIRONMENT=development, MAIL_DELIVERY=local and DEV_ENTITLEMENTS_ENABLED=true. Do not enable those development features in production. See the handoff for the full customer journey and production limitations.

Requirements: Python 3.12+, Node.js 22.9+ and npm; Node 24 is validated locally. The launcher can use the bundled Python runtime on this machine. If script policy blocks execution, use `powershell -ExecutionPolicy Bypass -File .\Start-Signal.ps1` for that process.

Manual backend startup from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Frontend from `frontend/`: `npm run dev`, or `npm run build` then `npm start` for an optimized build.

## Architecture and ownership

Next.js is the presentation layer. FastAPI owns authentication, authorization, ingestion, processing, scorecards, validation, review controls and reporting. SQLAlchemy/Alembic persist users, sessions, organizations, calls, transcripts, evaluations, scorecards and audit records. `/api` is a same-origin frontend proxy; backend OpenAPI is at `/docs`.

A registered account initially has no organization. After verification it can create one organization and become its OWNER. OWNER/ADMIN manage tenant users and scorecards; MANAGER/REVIEWER/legacy SUPERVISOR review interactions. EMPLOYEE has only basic account access pending scoped employee views. Operational roles also require a valid entitlement. Client-supplied tenant IDs cannot change ownership. Organization ownership is mandatory for calls and scorecards; audio, transcript, evaluation and audit ownership follows the authorized parent interaction. There is no cross-organization administrator UI or workspace switching.

Existing users, calls and scorecards migrate into `Signal workspace`. The fixed legacy organization ID is a migration/bootstrap identifier, not an authorization shortcut. User creation through the API is tenant-scoped. The trusted local CLI can provision an account in an existing organization:

```powershell
..\.venv\Scripts\python.exe -m app.cli person@example.com --name "Person Name" --role SUPERVISOR
```

The CLI optionally accepts `--organization-id` for an existing organization; by default it uses the migrated workspace. Passwords are entered interactively. This is an operator utility; new customers use browser registration. Newly provisioned accounts must verify through the account screen.

### Scorecards and QA

`services/rubric.py` centralizes validation and converts normalized rubric categories into provider instructions. `QAService.evaluate(text, rubric=items)` extends the existing abstraction; custom adapters must accept the rubric argument. OpenAI still uses Responses structured outputs with required category keys, bounded scores, and numbered exact source excerpts. The provider cannot submit total/max scores or rewritten quotations. `qa_contract.py` resolves source IDs, supplies maxima and calculates the total; the pipeline independently checks category presence, bounds, maxima, totals and verbatim evidence before saving.

A new attempt captures its scorecard before the provider request. Publication during that request does not change the evaluation's criteria. Explicit re-evaluation pins the active scorecard at request time; failed retries retain that captured version. Historical evaluations reference immutable published categories. The original six-category v1 rubric is seeded exactly by migration. Custom scorecards currently use weighted point categories totaling 100; criterion-level pass/fail, N/A, critical-failure rules and thresholds are not implemented yet.

### Speaker corrections and manual scores

Raw `Transcript.text` and `segments` are never edited by review commands. Derived conversation data carries exact source offsets and a raw-source fingerprint. A correction appends a record per affected turn, including original inference, previous/effective role, corrected role, scope, actor and time. Read views layer those records over inference without changing grouping or source words. Corrected speaker metadata is pinned as separate context for explicit reevaluation; raw evidence text remains unchanged. Whisper does not supply reliable audio diarization; bulk editing is offered only when a genuine speaker ID exists.

Evaluations have their own IDs and form an immutable AI history. Score-adjustment records are append-only, with null meaning reset. The final score is calculated from each category's latest effective adjustment, never a client total. A write lock and revision check reject stale concurrent review edits. Adjustments clear review completion; historical evaluations are read-only. Speaker correction and score history are visible on the detail page.

### Queue and storage

The database queue runs in one backend process with one worker thread. Transcription commits independently before QA. Restart recovery marks interrupted work failed; queued work persists. No automatic paid retries. Audio remains private under `backend/data/audio`, stored with generated names; uploads are streamed and bounded, signature-checked, and validated with audio metadata. Authentication is required for ranged audio responses.

The domain/API still uses `Call` and `/calls` internally for compatibility. The UI calls the library Interactions. A generalized ingestion-source model, batch upload and idempotent import keys are deferred; integrations must eventually enqueue through a shared ingestion service and reuse this downstream pipeline. No RingCentral, Zoom, Dialpad, live coaching, streaming or mobile client is implemented.

## Configuration

Backend `.env` (do not overwrite an existing file):

| Variable | Default | Purpose |
|---|---|---|
| DATABASE_URL | sqlite:///./data/drive.db | Existing database path remains compatible |
| UPLOAD_DIR | ./data/audio | Private recordings |
| FRONTEND_ORIGIN | http://localhost:3000 | Exact trusted browser origin |
| COOKIE_SECURE | false | Set true under HTTPS |
| SESSION_HOURS | 12 | Session lifetime, 1–168 hours |
| MAX_UPLOAD_MB | 24 | Per-file limit, 1–24 MiB |
| TRANSCRIPTION_PROVIDER | demo | demo or openai |
| QA_PROVIDER | demo | demo or openai |
| OPENAI_API_KEY | empty | Server-only provider credential |
| TRANSCRIPTION_MODEL | whisper-1 | Existing successful transcription model |
| QA_MODEL | gpt-4o-mini | Existing structured QA model |
| WORKER_ENABLED | true | Single-process queue worker |
| ENVIRONMENT | development | production enforces HTTPS, secure cookies and SMTP |
| DEV_ENTITLEMENTS_ENABLED | false | Explicit local-only seven-day test activation |
| MAIL_DELIVERY | disabled | disabled, local private outbox, or TLS smtp |
| MAIL_OUTBOX_DIR | ./data/mail-outbox | Private development messages containing one-use links |
| SMTP_HOST / SMTP_PORT | empty / 587 | STARTTLS mail transport |
| SMTP_USERNAME / SMTP_PASSWORD / MAIL_FROM | empty | Server-only SMTP credentials and sender |

Frontend `.env.local`: `BACKEND_URL=http://127.0.0.1:8000`. No secret belongs in `NEXT_PUBLIC_*`. Provider calls incur usage costs; no live requests were needed for this milestone's tests. Demo mode produces synthetic examples, never an analysis of uploaded audio.

## Database migrations and preservation

- `c301d927fb02`: normalized rubric/category tables; original v1 seed; evaluation IDs/history and rubric link; review metadata; speaker-correction and score-adjustment audit tables; pending rubric selection.
- `d402e038ac03`: organizations and required ownership, backfill into the legacy workspace, per-organization version uniqueness and one-active-scorecard constraint.

SQLite batch migrations temporarily disable foreign-key enforcement only on the dedicated migration connection, then run `foreign_key_check`. Application connections always enable it. Keep application processes stopped while applying migrations. Tests cover legacy data migration, exact original results, and foreign keys. The migrations were also rehearsed on a private copy of the existing database, preserving all original records; the live database was not migrated during development.

Do not downgrade a database with new audit/evaluation history or multiple organizations. The downgrade guards intentionally refuse data loss. Back up the database and audio together before deployment. Never delete data to resolve a migration problem. No user-facing deletion/retention policy is implemented yet.

## Verification

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m alembic check
```

Run Alembic check only after upgrading the selected database. From `frontend/`:

```powershell
npm run lint
npm run typecheck
npm run build
npx playwright test
```

Playwright starts temporary demo services on 3001/8001 using `.next-e2e`, a random test password, and an isolated database. It does not seed the user's database or send provider requests. It covers authentication, upload, queue completion, playback, transcript views, corrections, score overrides/reset, review completion, scorecard editing/publication, evaluation history and mobile reflow. Use `PLAYWRIGHT_CHANNEL=msedge` for Edge if Chrome is unavailable. See `SIGNAL-QA.md` and `SIGNAL-HANDOFF.md`.

## Production and mobile continuation

The backend boundary can be reused by React Native/Expo. Authentication currently uses opaque HttpOnly sessions and same-origin CSRF defenses; design a secure mobile session/token flow before adding a native client. Do not duplicate QA or tenant policy in a mobile UI.

This is not yet safe to market as a publicly onboarded paid SaaS. Account entry, verification/recovery and a development entitlement gate now work locally. Remaining launch work includes production email delivery/abuse hardening; employees and assignment; batch ingestion/idempotency; richer scorecard criteria; analytics/coaching; production entitlements, usage and real billing integration; administrative audit expansion; retention/account deletion; PostgreSQL deployment verification; distributed worker leases/timeouts; observability, backups/restore drills, and production security review. Dashboard aggregation currently targets small local datasets and should move to scoped SQL aggregates as data grows.

For eventual `signal.zoqari.com`, configure HTTPS, secure cookies, exact origin, a private database/audio store, reverse-proxy upload limits and shared rate limiting. Validate PostgreSQL migrations before deployment. Do not run multiple backend workers with the current in-process queue. No DNS, corporate-site or public deployment configuration was changed.

## Brand provenance

The corporate project at `C:\Users\Thoma\Documents\Zoqari` was used read-only. `BRAND.md`, its CSS, header, self-hosted type and original branding board were inspected. Signal copies the approved raster crops without recoloring/reconstruction. Sora is used for compact headings, Inter for UI/body, Midnight for navigation and Blue for primary actions. Cyan is restrained. The corporate project remains untouched. Historical documents and internal compatibility identifiers may still mention DRIVE; the current product identity is Zoqari Signal.
