# Deployment repair — 2026-09-26

This checkpoint supersedes older deployment statements below. Scope: repair Vercel API routing and the confirmed broken branding-image request only. The commercial-beta milestone is not being resumed in this repair. Git is now present; starting HEAD was `4d8a1bc` (clean working tree), after `45585a7` (Services), `2ccae9b` (Python project metadata) and `4d8a1bc` (module-level FastAPI app). Those deployment fixes remain intact. No application endpoints, providers, authentication logic, database schema, workers or corporate-site files changed.

## Root cause and observed deployment

Read-only checks of `https://zoqarisignal-alpha.vercel.app` on 2026-09-26 confirmed:

- `/api/account`, `/api/preferences`, `/api/auth/options`, `/api/health`: HTTP 404, `x-vercel-error: DNS_HOSTNAME_RESOLVED_PRIVATE`.
- `/login`: HTTP 200.
- All four `/brand/*.png` assets: HTTP 200 with `image/png`.
- `/_next/image?url=%2Fbrand%2Fz-mark.png&w=256&q=75`: HTTP 404 (also broken on the current alias, not just the old deployment-specific hostname).

The browser API contract is `/api` plus the existing backend endpoint. This includes `lib/api.ts`, preference loading, multipart XHR single/batch upload, audio playback, and the employee CSV template link. FastAPI exposes unprefixed `/account`, `/preferences`, `/auth/*`, `/calls/*`, etc. Locally, `next.config.ts` rewrites `/api/:path*` to `${BACKEND_URL || "http://127.0.0.1:8000"}/:path*`, removing `/api`.

The original Vercel service rule matched only `/api/backend/(.*)`. Real `/api/*` requests fell through to Next.js and its local proxy. The private-hostname error is consistent with Vercel attempting that loopback destination; remote environment values were not inspected. Changing only the service rule would still fail: service rewrites preserve the original request path, while FastAPI has no `/api` prefix.

## Fix and routing contract

`vercel.json` now sends `/api/(.*)` to `backend` before the frontend catch-all. A **backend service-local** `request.path` transform sets `/$1`, stripping exactly the public prefix before FastAPI sees it. This follows Vercel's [service path-transform example](https://vercel.com/docs/project-configuration/vercel-json#request-path-transform-in-a-service) and current [Services guide](https://vercel.com/kb/guide/vercel-services). `destination.path` alone is not equivalent: it selects a service route but does not change the runtime-visible path. Older `experimentalServices`/`routePrefix` documentation does not describe this repository's current `services` configuration.

| Public request | Service | Runtime path |
| --- | --- | --- |
| `/api/account` | backend | `/account` |
| `/api/preferences` | backend | `/preferences` |
| `/api/auth/login` | backend | `/auth/login` |
| `/api/calls/id/audio` | backend | `/calls/id/audio` |
| `/api/batches/id/items/id/upload` | backend | `/batches/id/items/id/upload` |
| `/api/billing/webhook` | backend | `/billing/webhook` |
| `/api/employee-imports/template.csv` | backend | `/employee-imports/template.csv` |
| `/`, `/login`, `/register`, `/employees`, `/rubrics`, `/upload`, `/team` | frontend | unchanged |
| `/brand/*`, `/_next/*` | frontend | unchanged |

The same rule covers all **69 OpenAPI paths / 78 operations**, including flags, team/invitations, account/onboarding, preferences, hierarchy, admin, briefing, scorecards and evaluation history. It does not list or duplicate individual endpoints. Methods, body, query, cookies, Origin, request-verification header and Range remain intact. The path transform also preserves the exact backend webhook path used by the existing CSRF exception; Stripe signature verification remains authoritative. Unknown API routes remain backend 404s, not page fallbacks. `/dashboard` is not currently a Next page (the dashboard is `/`); it remains a frontend 404 rather than becoming the backend `/dashboard` API.

Local `next.config.ts`, browser API construction and FastAPI endpoints are unchanged. `frontend/.env.example` now explains that `BACKEND_URL` is for local/non-Services proxying; Vercel's direct service route needs no public backend hostname or frontend API-base variable.

For branding, `components/ui.tsx` uses Next Image's `unoptimized` property on the two existing static PNGs. Requests go directly to the confirmed-working `/brand/z-mark.png` and `/brand/wordmark.png`, avoiding the broken deployed optimizer route. Artwork, layout, dimensions, alt text and CSS are unchanged. This addresses the visible asset failure without altering global image handling or chasing preload warnings; it does not claim Vercel's image optimizer itself was repaired.

Files changed in this repair: `vercel.json`, `frontend/.env.example`, `frontend/components/ui.tsx`, `backend/tests/test_deployment_routing.py`, `frontend/tests/api-routing.spec.ts`, and this handoff.

## Validation

- New routing suite: **21 passed**. Checks every actual FastAPI operation against service selection and prefix stripping, frontend/static exclusions, authenticated account/preferences and representative resources, login cookie, CSRF rejection, multipart upload and ranged audio.
- Full backend suite: **242 passed, 2 failed**. Both failures were independently reproduced on a temporary clean archive of starting HEAD `4d8a1bc`, with no repair files present. `test_migration_preserves_legacy_transcript` expects downgrade through a populated audit-reference migration that intentionally refuses data loss. `test_employee_edit_deactivation_permissions_and_tenant_scope` round-trips read-only email/external-ID response fields into the strict employee-write schema, receiving 422. These pre-existing beta regressions were documented rather than changing unrelated application behavior or weakening validation.
- Backend Ruff: passed. Module-level `app.main:app` import: passed, title `Zoqari Signal API`; secure production-settings import and public-options/anonymous-account/preferences checks also passed using dummy SMTP configuration without sending mail. Tests and startup used temporary/in-memory storage, demo providers, disabled external integrations; no live source database was opened for validation, migrated, reset or deleted.
- Frontend ESLint, TypeScript and production build: passed after the asset change.
- Browser final run: **6 passed, 1 failed** across `api-routing.spec.ts`, `customer-entry.spec.ts`, and `workflow.spec.ts`. Registration/verification/onboarding, pre-hydration safety, upload/process/playback/mobile, transcript controls and scorecard/review history pass. The existing password-recovery test has a stale exact link selector (`Reset password` versus the rendered `reset your password`); both the test and verification UI are byte-equivalent to HEAD after line-ending normalization. This is a test-selector issue, not evidence that recovery API routing is broken. The new routing/asset browser test already passed: anonymous account/preferences return FastAPI JSON 401 (not routing 404), health/options return 200, page routes stay HTML, and both logos load directly without `/_next/image`.
- `vercel.json` parsed and validated against the freshly retrieved official `https://openapi.vercel.sh/vercel.json` property schema. The upstream schema advertises draft-04 while containing newer keywords; Ajv meta-schema self-validation was disabled to compile that upstream document, with configuration/property validation retained. This is structural validation, not an actual Vercel deployment.
- Local mapping tests model documented Vercel routing semantics. They do not execute Vercel's edge. The repair has **not** been pushed or redeployed, so the live alias still requires post-deployment verification.

## Exact next Vercel actions

1. Review, commit and push the six repair files on the branch Vercel deploys. Do not add `.env`, local databases, uploaded recordings, private outbox, traces or credentials. No commit/push/deployment was performed during this repair.
2. In Vercel, keep the project's Framework Preset **Services**, repository root at the directory containing `vercel.json`, frontend root `frontend/`, backend root `backend/`, entrypoint `app.main:app`. Preserve the Python 3.12 configuration and existing `pyproject.toml` project metadata. Do not replace this with a frontend-only root directory.
3. No `NEXT_PUBLIC_BACKEND_URL`, `/api/backend` base or public backend hostname is needed. Do not set `BACKEND_URL` to the app's own public `/api` URL (proxy loop). The existing local value remains appropriate only for local development; the Services router now bypasses that proxy for API calls.
4. Configure the backend's secure runtime settings below before using real accounts/recordings. Keep deployment protected until the storage/worker blockers are resolved. Do not use a development entitlement or local mail as a production workaround.
5. Redeploy and use the current alias. First request `GET /api/auth/options` (public, no DB requirement in handler), then `GET /api/health` (DB connectivity). In a private window `/api/account` and `/api/preferences` should return **401 JSON**; after valid sign-in they should return **200 JSON**. A 500/503 now indicates backend configuration/startup/storage, not the old Next.js routing 404. Check Vercel backend invocation logs without sharing sensitive environment values.
6. Verify `/login`, `/register`, `/`, `/employees`, `/rubrics`, `/upload`, `/team`, direct `/brand/*` assets, and authenticated API calls with queries. Browser logo requests should be direct `/brand/*.png`. Use only synthetic data for any upload smoke test until persistence and worker operation are demonstrated. Check a state-changing request has the exact trusted Origin and `X-Drive-Request: 1`; do not relax CORS/CSRF to make it pass.
7. Once the custom domain is ready, add `signal.zoqari.com` to this same Vercel project and apply only Vercel's actual DNS instructions. Set `FRONTEND_ORIGIN=https://signal.zoqari.com` and update the Stripe webhook address accordingly, then redeploy. Preview URLs need separately scoped configuration; the app intentionally trusts one exact origin, not arbitrary deployment hosts.

## Production infrastructure still required (separate from routing)

Actual remote environment values/credentials were not inspected or changed. These are code/platform requirements, not claims that Thomas has or has not configured a particular external account.

- **Database:** default `DATABASE_URL=sqlite:///./data/drive.db` creates directories and uses a local SQLite/WAL file. Vercel Functions are not a durable shared SQLite host. Use a managed persistent database via `DATABASE_URL` (the installed driver supports `postgresql+psycopg://...`), TLS, suitable connection pooling, backups and a PostgreSQL migration rehearsal. Apply Alembic `upgrade head` in a controlled release job before serving the new app; importing `app` does not migrate schemas. Do not reset the development database or copy private DB files into Git.
- **Recording storage:** `create_app()` creates `UPLOAD_DIR` at import; ingestion, playback, transcription and cleanup all use local paths. A read-only deployment filesystem can prevent startup. `/tmp` can make an isolated smoke test boot but is ephemeral, instance-local and **not a production storage fix**. Durable private shared/object storage requires a follow-up adapter/deployment decision; the current app has no S3/Blob environment setting that magically makes local audio durable.
- **Worker:** lifespan starts an in-process daemon thread. Restart recovery changes transcribing/analyzing records to failed; autoscaled API instances can interfere with another instance's work. A serverless response does not guarantee that the thread continues processing. Set `WORKER_ENABLED=false` for Vercel API-only smoke tests, recognizing accepted jobs then remain queued. Real processing needs an explicitly designed durable worker/queue or a supported persistent single-process backend deployment. Also review the in-memory account/login/coaching locks and rate limits before autoscaling. [Vercel's FastAPI runtime scales as a Function](https://vercel.com/docs/frameworks/backend/fastapi); a successful build proves neither durable processing nor persistent files.
- **Upload limits:** Signal accepts up to 24 MiB, while the documented [Vercel Function payload limit is 4.5 MB](https://vercel.com/docs/functions/limitations). The local Next.js 26 MB proxy setting does not override the platform limit. Larger recording uploads/audio responses need an appropriate durable-storage/direct-transfer or hosting design; no limit workaround was added here.
- **Production security/origin:** explicitly set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `DEV_ENTITLEMENTS_ENABLED=false`, `MAIL_DELIVERY=smtp`, and `FRONTEND_ORIGIN=https://zoqarisignal-alpha.vercel.app` while that is the intended origin (no trailing slash). The code's omitted environment default is development; Vercel's deployment label alone does not set this application variable. Production validation rejects insecure cookies, non-HTTPS origins, local mail and development grants. Do not bypass those errors. Browser/backend calls stay same-origin, so no permissive CORS addition is needed.
- **Authentication secrets:** this application uses random opaque HttpOnly cookie sessions, SHA-256 token hashes and Argon2 passwords in the database. It does not currently require an invented JWT/SESSION_SECRET setting. Database persistence and HTTPS are required for reliable sessions. Keep `SESSION_HOURS` within the existing validated range.
- **SMTP:** configure `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM` (verified sender such as `Zoqari Signal <accounts@zoqari.com>`), TLS network access and provider-required DNS. SMTP uses certificate-verified STARTTLS. No live email delivery was tested; local outbox is forbidden in production.
- **Stripe:** code already exists in HEAD; it was not expanded in this repair. Configure server-only `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_MODE`, and all six `STRIPE_PRICE_{STARTER,BUSINESS,PRO}_{MONTH,YEAR}` IDs. Hosted Checkout/Portal also need corresponding Stripe account settings. External webhook URL is `https://<app-domain>/api/billing/webhook`, with existing checkout/subscription/invoice events enabled. Current code grants test entitlements only in development and live entitlements only in production; do not enable dev bypass to simulate a paid production account. No Stripe account IDs, secrets or live billing claims were invented.
- **OpenAI:** for real processing explicitly set `TRANSCRIPTION_PROVIDER=openai`, `QA_PROVIDER=openai`, `OPENAI_API_KEY`, `TRANSCRIPTION_MODEL`, `QA_MODEL`. Existing demo defaults are synthetic. Never place provider credentials in `NEXT_PUBLIC_*`. No paid requests were made in this repair.
- **Remaining quality/security work:** the two baseline test failures above, external delivery/payment verification, migration/restore rehearsals, shared abuse controls and prior incomplete commercial-beta validation remain open. Routing repair is not a production-readiness certification.

Recommended next step: redeploy the routing repair in a protected environment and confirm FastAPI JSON responses. Then resolve the database/audio/worker hosting decision before accepting customer recordings or paid customers.

---

# Signal handoff — owner dashboard delivered; commercial beta work in progress

## Owner dashboard checkpoint — 2026-09-23

WORKING NOW: owner briefing at `/briefing`, deterministic below-maximum category issues separated by immutable rubric ID/version/key/max, current latest audited totals only, stale and superseded exclusion, current direct-report weighted team scores, evidence pagination and explicit AI-assisted coaching/email drafts. New-user modules: metrics, attention, issues, teams, coaching, recommendations, recent. Existing saved module arrays remain exactly unchanged; review and optional processing still supported. Editor supports visibility, accessible move controls, restore, cancel and revision-checked save. All-time/current-assignment period is explicit; no trends are invented.

AI boundary: `CoachingService` uses the configured QA provider/model through its own registry. Only bounded aggregate counts, exact category requirements/description and anonymous score distributions reach it. Structured output selects one of three proportionate review actions and warm/concise tone. Signal supplies factual wording and requirements. No free-form invented policy, cause or disciplinary text is accepted. At least five eligible evaluations on the exact standard and two occurrences are required. The three highest occurrence patterns form review priorities. Explicit Generate/Regenerate may incur provider usage; refresh never generates. Cached action/tone persists per organization/issue and data fingerprint; all supporting evaluation IDs, audited revisions, employee/manager assignments and scores invalidate stale output. Editable drafts are local to the dialog; copy only, no sending. Synthetic data is labeled in draft text. Normal auth, verified membership, entitlement and review role apply; Employee denied, guessed foreign issue IDs return 404.

Migration `k179570fac10` adds only `coaching_drafts` (bounded choice and fingerprint/provider metadata, no transcript or employee content). It does not change preferences or historical data; populated-table downgrade refuses data loss. Latest evaluation ties now use created_at then ID consistently in Call and briefing. Snapshot batch-loads latest evaluations, scorecards, overrides/actors and correction revisions; no N+1 per-call lookups. UI uses one briefing fetch on entry/manual refresh rather than per-component polling.

Validation: **199 backend tests pass**, including 18 briefing cases. Ruff, frontend lint/types/production build pass. All **13 browser workflows verified**: 12 existing in the full run, new owner workflow passed targeted after scoping the dialog selector and giving its textarea an explicit accessible label. Evidence, AI/demo action, draft review/edit/copy/no-send, manager navigation, hide/reorder/cancel/refresh and mobile tested; previous session-persistence coverage preserved. Screenshots inspected. Private-copy rehearsal preserved all original columns/rows including **3 users, 8 calls, 8 transcripts, 11 evaluations**, FK and Alembic checks pass; live DB unchanged. No live AI/mail requests.

FOUNDATION ONLY / limitations: weighted categories are not criterion pass/fail; no attribution of which sub-requirement failed. AI choices are deliberately bounded, not unconstrained prose. Communications scope is organization-wide, with manager evidence links; no per-team generation filter, delivery, or saved user-edited draft. All-time summaries, no date/trend claims. Snapshot uses Python aggregation over organization current data, with bounded query count but no large-enterprise load claim. Single-process generation lock; no distributed jobs. SMTP, Stripe, flagged terms, code verification, imports and beta-readiness work are the active next milestone, not yet claimed complete.

Restart `Start-Signal.ps1` when ready to apply the migration. Existing saved users can enable new modules or Restore defaults. No re-upload/transcription is needed.

## Commercial beta active plan

See BETA-PLAN.md. User now authorizes corporate `/products/signal` edits only after Signal-side work is stable and tested. Earlier corporate read-only restriction is superseded for that bounded phase. No Git repository exists; no recent commits to inspect. Existing source checkpoints are retained.

---

# Signal handoff — product corrections and administrative controls

## Current delivery boundary — 2026-09-21

This milestone corrects manager eligibility, enables explicit grading-standard selection and adds safe Owner/Admin deletion/archive controls. The historical sections below are superseded where they describe derived manager designation, a single active scorecard or no deletion controls. The working authentication, provider abstraction, transcription, correction context, strict QA validation, employee attribution, invitations and dashboard preference architecture remain in place. No Git repository is initialized in this directory; prior source milestone archives were preserved as comparison checkpoints.

### WORKING NOW

**Manager designation.** `Employee.manager_eligible` is an explicit boolean, false by default, controlled through **Can manage employees** on employee create/edit. It is independent of job title, User linkage and login role. The employee table labels Employee/Manager. New reporting assignments require an active, same-organization, manager-eligible Employee. Existing inactive reporting relationships may be retained or removed. All existing self/deep/concurrent cycle protection and revision checks remain. Manager selectors and team lists use explicit eligibility; eligible managers with zero reports are now included. A normal employee has no team-performance link and its team endpoint rejects that request.

Migration designates only Employees who already have direct reports; it does not alter those reporting relationships or mark everyone as a manager. Removing designation is blocked with a report count until **all** direct reports, including inactive reports, are reassigned or removed. Designation changes append an administrative event. Owner/Admin/Manager retain the existing employee-management permission; designation does not grant login access.

**Multiple published scorecards.** Published content remains immutable. Publishing a draft no longer archives other versions automatically. Multiple scorecards/versions can remain published simultaneously. The internal `ACTIVE` status means **PUBLISHED** in the UI; legacy `/rubrics` routes and version IDs remain compatible. Owners/Admins explicitly archive published versions when they should no longer be selected. Historical evaluations continue resolving their exact rubric ID/version/categories. Version labels retain the existing organization-wide numbering; there is no new parallel rubric or scorecard-family system.

**Single upload.** The upload page requires a visible published Scorecard choice before Upload & process. Multipart `rubric_id` is validated against the authenticated organization and publication state before audio ingestion. The chosen ID is persisted on the queued Call before transcription/QA and controls the rubric passed to the provider and independent result validator. Later publication/archive does not retarget an accepted call. API clients omitting `rubric_id` retain compatibility: the most recently published available version is captured at ingestion, not selected later by the worker. The UI always sends the chosen ID.

**Bulk upload.** Choose one published Scorecard for the batch. `UploadBatch.rubric_id` and the visible name/version identify it; each new accepted Call pins that version. Reusing a manifest request key with a different explicit scorecard returns 409. Exact-byte duplicates still avoid a new paid request when the existing interaction's requested/latest scorecard matches. A duplicate with a different scorecard fails that item with an explanation to open the existing interaction and use New QA evaluation, or choose its scorecard. It never silently grades against the wrong standard or replaces previous results. If a batch's scorecard is archived before an outstanding file is ingested, that file is rejected; create a new batch with a published selection. Already accepted calls and QA retries retain their pinned version. Legacy manifests with no stored selection retain default-on-ingestion behavior.

**New QA evaluation.** Reviewers can select any same-organization currently published scorecard. The confirmation names the exact version and explains QA usage and preservation of history. The existing transcript is reused, current corrected speaker context is captured, and a new Evaluation is appended. A provider result using the wrong category contract is rejected; validation was not relaxed.

**Evaluate corrected transcript.** This remains a separate action pinned to the previous evaluation's scorecard/version, even if now archived. The API uses explicit `use_previous_scorecard=true` and rejects a different ID in that mode. The ordinary new-evaluation mode rejects archived/draft versions. Both preserve prior evaluations and capture current speaker revision. Failed QA Retry still reuses committed transcription and its pinned attempt context.

**Interaction deletion.** Owner/Admin has a separate Administrative controls panel with a destructive dialog requiring `DELETE`. Server authorization/tenant ownership is mandatory. Transcribing/analyzing calls return 409 until processing finishes. Queued calls can be removed before the worker claims them; DB row locking makes claiming/deletion mutually exclusive. Deletion atomically removes the Call, raw/derived transcript, speaker corrections, all evaluations/context/review state, score overrides and call assignment history. All current organization/employee/manager/review metrics then naturally exclude the interaction. Employees, Users, scorecards and unrelated records remain.

All batch/duplicate links to the removed Call become non-uploadable **Deleted interaction** tombstones with no call ID, original filename or size. The manifest remains readable and counts deleted entries separately. The recording hash disappears with the Call; an intentional new upload may be processed again. Repeating the same call DELETE is safe for that organization.

**Audio cleanup.** The database transaction records a private durable `pending_audio_deletions` item before committing content deletion. The endpoint immediately tries to unlink the original private recording. Only a resolved path inside the configured audio directory is eligible. Success removes the cleanup item and appends a completed audit event. Filesystem failures leave a durable job, return `audio_deletion_pending` and show a pending-cleanup notice; no completed-audio-deletion claim is made. The enabled single-process worker retries cleanup on subsequent polls/restart. A repeated authorized DELETE also retries cleanup. The removed Call makes audio inaccessible through Signal even while physical unlink is pending. Cleanup logs only call ID and error type. It makes no provider requests.

**Employee archive/delete.** Owner/Admin can explicitly Archive employee, preserving performance, User links, reporting relationships and all histories while blocking new assignments. Active selectors exclude archived people. Existing employee-details Active employee restores the record under the existing employee-management permission. The historical ability for Manager-role users to change employee active state is preserved; the new archive endpoint and all permanent deletion commands are restricted to Owner/Admin.

Permanent employee deletion is limited to unused records with no current interactions, assignment-history references (including previous employee IDs), direct reports, current manager, reporting/link audit dependencies or linked User. Blocks return dependency counts and recommend Archive. It does not cascade into business QA history. Content-free administrative metadata may remain after a safe unused-employee deletion.

**Administrative audit.** Append-only `admin_events` stores actor, organization, resource type/ID, action and timestamp, with no audio, transcript, result payload, filename, password or free-text deletion reason. Call deletion records request/content removal (`audio_deletion_pending`) and successful audio removal (`deleted`) as separate events. Employee delete/archive/restore and designation changes are recorded. Owner/Admin can read the latest 100 own-organization events at `/admin/events`. Existing reporting/link and surviving call review audits remain unchanged.

### ARCHITECTURAL FOUNDATION ONLY

- Employee ↔ User linking still identifies a person without changing permissions. Manager-only team access and employee self-service remain future work.
- Durable audio cleanup is a local single-worker recovery mechanism; it is not a distributed storage/retention system.

### NOT YET IMPLEMENTED / known boundaries

- Per-file scorecard override, automatic scorecard selection, scorecard-family version numbering or bulk reassignment. Batch-level choice is implemented.
- Background cancellation of a paid in-flight provider request. Wait for it to finish/fail before deletion.
- Automatic retention policies, secure physical media erasure, backup purging or provider-side deletion. Deletion targets active application database records and private audio files; operator backups, including private migration rehearsal copies, have their own lifecycle.
- A graphical audit-log explorer; the scoped latest-100 audit API is available. There is no optional free-text deletion-reason field.
- Public billing/deployment, external integrations, HRIS, payroll/scheduling, live coaching/listening, mobile, gamification or historical-as-of analytics.
- Existing small-dataset performance aggregation and single-process worker limits remain. Saved dashboard module preferences and appearance were not migrated or reset.

### Schema and API changes

Migration `j068469efb09` follows `i957358dfa08`. Adds `employees.manager_eligible`, nullable `upload_batches.rubric_id`, `admin_events` and `pending_audio_deletions`; removes the one-active-rubric partial unique index. Existing published scorecard content/status and evaluation payloads are untouched. Existing managers are backfilled from actual direct reports. Downgrade is allowed only when no new control/audit/link state or multiple-publication state would be lost; otherwise restore a verified backup.

| Endpoint | Contract |
|---|---|
| POST /employees; PUT /employees/{id} | Explicit manager_eligible; existing management roles, scoped revision/cycle/dependency checks |
| GET /employees?managers_only=true | Explicit designated managers, optionally active=true; no longer derived from report count |
| POST /calls | Optional legacy-compatible multipart rubric_id; UI requires a published selection |
| POST /batches | Optional legacy-compatible rubric_id pinned on the manifest and accepted new calls |
| POST /calls/{id}/reevaluate | Published rubric_id, latest evaluation_id, transcript_revision; optional use_previous_scorecard for pinned correction |
| POST /rubrics/{id}/activate | Publishes immutable version without archiving other published versions |
| POST /rubrics/{id}/archive | Explicit revision-checked archive, including published versions |
| DELETE /calls/{id} | Owner/Admin; terminal/queued calls only; content deletion plus durable audio cleanup |
| POST /employees/{id}/archive | Owner/Admin, revision required; no history deletion |
| DELETE /employees/{id} | Owner/Admin, revision required; dependency-checked permanent deletion |
| GET /admin/events | Owner/Admin, own organization, latest 100 content-free events |

All new commands preserve verified account, active entitlement, existing Origin/header checks and server-side organization isolation. Manager/Reviewer/Supervisor/Employee cannot permanently delete. Cross-tenant scorecard selection, reevaluation, hierarchy mutation, deletion/archive and audit retrieval are tested.

### Validation and restart

- Baseline: 165 backend tests. Final backend suite: **181 passed**, including 16 new product-control cases plus updated hierarchy/publication regression expectations. Ruff passed.
- Frontend lint, typecheck and optimized build passed. All 12 browser workflows verified (11 in the final full run; both new workflows passed on the targeted rerun after a test-navigation synchronization fix). Destructive-dialog and batch-tombstone screenshots inspected. Exact commands/results are in SIGNAL-QA.md.
- Private-copy migration rehearsal preserved every original column/row: **3 users, 8 calls, 8 transcripts, 10 evaluations**, and all other original tables. Foreign-key integrity and `alembic check` passed. A separate synthetic migration test proves only prior reporting targets become manager-eligible.
- No real recordings were deleted, no live database migration/reset occurred, and no live AI requests were made. Test deletions use temporary databases/audio only.

Stop the current local launcher and restart with `Start-Signal.ps1` to apply the tested migration. No new dependencies or environment changes are required. Existing data/providers/credentials remain. Existing managers with reports remain designated; edit any other intended manager and check Can manage employees. Publish additional scorecards, choose one before single/bulk upload, and use New QA evaluation to intentionally change standards on saved transcripts. No re-upload is required to regrade an existing completed interaction.

## Historical delivery record — hierarchy milestone

# Signal handoff — organizational hierarchy

## Current delivery boundary — 2026-09-20

This focused milestone extends the existing Employee model and current performance service. Authentication, invitations, transcription, QA validation, correction/retry behavior, call assignment, bulk upload and personal dashboard preferences remain intact. This section supersedes the historical milestone records below where behavior differs.

### WORKING NOW

- An Employee has an optional direct `manager_id` referencing another Employee in the same organization. User remains the login account; Employee remains the tracked organizational person. A manager is naturally an Employee with current direct reports, independent of job title and login. Any active Employee can be selected as a reporting target, including someone with zero reports. There is no redundant `is_manager` flag.
- Employee creation/editing includes an ID-based searchable Manager selector and No Manager. Profile shows the current manager, direct reports, links to their profiles and current team performance. Owner/Admin/Manager may edit employees and reporting; Reviewer/legacy Supervisor may read. Existing Manager role permissions remain organization-wide.
- Self-management and cycles of any depth are rejected. An organization row lock serializes reporting, deactivation and login-link mutations; stale employee revisions return 409. Foreign-organization IDs return 404. An older client that omits `manager_id` during edit preserves the existing relationship.
- Manager changes append `employee_hierarchy_changes` with employee, previous/new manager IDs, actor and time, including initial assignment and removal. Optional login link changes use the same append-only audit. Profile displays history; names are resolved from current person records, while IDs/time remain historical.
- Deactivating a manager retains direct reports, assignment/audit history and current attributable analytics. Inactive state is visible on profiles and team pages. New reports cannot be assigned to an inactive manager; retaining an unchanged relationship, removing it or moving to an active manager is allowed. Inactive direct reports remain in the team and their eligible interactions continue to count.
- Employees → Manager teams lists people with current direct reports and supports search, pagination and sorting by name, team score or interaction count. A manager losing their last report disappears from that list, while their profile/team URL remains available with empty metrics. No manager login is required.
- `/employees/{id}/team` shows current direct reports, their scores and interaction counts, team score/analyzed/review counts, outdated and failed counts, category point averages by published scorecard version, and ten recent team interactions. Missing scores remain empty; fewer than five eligible evaluations is labeled a limited sample.
- Interactions provides server-side Manager filtering and a narrowed searchable Employee selector. Changing Manager resets Employee. Combining compatible IDs further narrows results; contradictory manager/employee combinations return 422. Specific foreign employee IDs now return 404 rather than an empty result. `manager_id=unassigned` includes both assigned employees with no manager and interactions with no employee. Employee-list No Manager includes only employees with no manager.
- Owner/Admin can explicitly link/unlink one Employee to one same-organization User from the profile. The database enforces one Employee per linked User. No name/email matching or new account creation occurs. New links require both records active; existing links survive deactivation and can be removed. Link changes require the employee revision and are audited. The link grants no access and changes no role.

### Team Signal Score and attribution

Collect calls assigned to Employees whose **current direct manager** is the selected Employee. Reuse `services.performance.current_performance`: each call contributes its latest persisted successful evaluation exactly once only if its captured speaker-correction revision is current. Apply the existing audited category overrides to that evaluation. Average these final 100-point scores, rounded to one decimal. Do not average employee averages. For example, two 90-point calls for John and one 80-point call for Maria produce 86.7, not 85.

Superseded/outdated evaluations never count; their stored history remains intact. A pending/failed attempt does not erase a prior eligible result. Category averages use the existing rubric-version/category/max grouping. Review attention means the latest evaluation is outdated or not marked reviewed; failed processing is separately counted. A manager's own calls are excluded from their own team. Indirect reports are excluded. Moving Maria to David moves all her currently assigned interactions into David's current team view; it does not rewrite call assignments, transcripts or evaluations. This is current-state attribution, not historical-as-of reporting.

### ARCHITECTURAL FOUNDATION ONLY

- The explicit unique Employee ↔ User link can identify a logged-in manager's employee record for a future scoped-access milestone. **No own-team access policy is enabled.** Existing roles, tenant boundaries and entitlement checks remain authoritative; a link never broadens access.
- Reporting-change IDs and timestamps preserve the basis for possible future historical attribution. No date-based team reconstruction is implemented.

### NOT YET IMPLEMENTED / bounded limitations

- Manager-only team access, employee self-service, recursive organizational rollups and historical-as-of analytics.
- New dashboard modules: this milestone uses Employees → Manager teams and leaves saved dashboard modules/order/appearance untouched.
- Large-enterprise analytics optimization: team summaries reuse the existing Python current-evaluation service, query only the authenticated organization and sort on the server. The list returns 50 managers per page but calculates matching team summaries before paging. Large datasets may require a measured query/aggregation optimization milestone. Employee/manager pickers return up to 100 search matches; type a name to narrow.
- No integrations, live listening/coaching, arbitrary AI manager ratings, rankings/gamification, payroll, scheduling, HRIS, org-chart builder or billing/public deployment.

### Schema and APIs

Migration `i957358dfa08` follows `h846247cef07`. It adds nullable `employees.manager_id` (indexed self-FK), nullable unique `employees.linked_user_id` (User FK), and `employee_hierarchy_changes`. Existing employees start without inferred manager/login links. Downgrade refuses to discard reporting/link or audit data.

| Endpoint | Change |
|---|---|
| POST /employees; PUT /employees/{id} | Optional manager_id, scoped and cycle-checked; edit uses existing revision |
| GET /employees | manager_id / unassigned and managers_only filters alongside search/status/pagination |
| GET /employees/{id} | Includes manager_id; existing personal performance unchanged |
| GET /employees/{id}/hierarchy | Current manager, reports, optional linked user and audit history |
| PUT /employees/{id}/user-link | Owner/Admin only; user_id or null plus revision; audited unique link |
| GET /manager-teams | Current managers, q, sort=name/score/interactions, offset; 50 per page |
| GET /employees/{id}/team | Current direct-report team metrics/members/categories/recent calls |
| GET /calls | manager_id / unassigned; combined employee filter validated server-side |

### Data safety and validation

Migration rehearsal used an online SQLite backup in private `backend/data/rehearsals`, compared every original table/column/value, and passed foreign-key integrity plus `alembic check`. Exactly preserved: **3 users, 8 calls, 8 transcripts and 10 evaluations**, plus all other original records. The live database was not migrated or reset. No live provider requests were made; automated tests use temporary databases and synthetic recordings.

- Backend: **165 tests passed**, including eight new hierarchy regressions for assignment/removal/history, self/deep/concurrent cycles, inactive-manager behavior, weighted/current/overridden scores, moves, reassignment, tenant ID manipulation, account-link uniqueness/audit/revisions and unchanged role permissions.
- Ruff, frontend ESLint, TypeScript and production build passed.
- All 10 browser workflows pass: nine existing workflows in the full run and the new hierarchy workflow on its targeted rerun after a test-selector correction. Desktop light/dark and mobile screenshots were inspected. See SIGNAL-QA.md for exact commands and results.

Restart the existing application through `Start-Signal.ps1` after stopping its current services. The launcher applies the new migration; existing data and configured providers remain in place. Then create reporting targets as Employees, assign managers in employee details, and open Employees → Manager teams. No recording re-upload or retranscription is required.

## Historical delivery record — Day 2 Part 2

# Signal handoff — Day 2 Part 2 operations

## Current delivery boundary — 2026-09-20

Day 2 Part 1 remains intact. Part 2 adds persisted bulk ingestion, employee attribution, corrected-transcript QA consistency, team invitations, personal dashboards, and Light/Dark/System appearance. This is a working local milestone, not a public SaaS launch or paid subscription implementation. The historical Part 1 and Day 1 records below are superseded where this section describes new behavior.

### WORKING NOW

- Bulk upload at `/batches`: select/drop up to 100 files, per-file format/size checks, independent upload progress and server status, persisted manifest/history/counts, individual replacement/retry, and navigation away/return. Accepted files are ordinary Call records processed by the existing server queue.
- Exact-byte SHA-256 duplicate protection within the authenticated organization. Duplicate batch items link to the existing interaction and do not queue another transcription/QA request. Manifest request keys and individual item claims prevent accidental duplicate submissions.
- Tenant-owned Employee records independent from login User accounts. Owner/Admin/Manager can create, edit, deactivate, reactivate, search, and assign employees. Reviewer/legacy Supervisor can read profiles but cannot change employees or assignment. No employee is hard-deleted; old calls remain unassigned until explicitly attributed.
- Interaction detail assignment/reassignment/unassignment with actor/time/previous/current employee audit and conflict detection. Interaction list includes employee and supports an employee/unassigned filter. Employee profiles show actual current score, assigned/current/stale counts, version-specific category averages, recent interactions, and sourced strengths/coaching. Sparse samples are labeled; missing scores remain empty.
- Speaker correction makes an older evaluation visibly outdated immediately. Raw transcript text/segments, original inference and AI results remain unchanged. Outdated scores do not contribute to current interaction, employee, or organization Signal Score. They remain available for historical inspection and supervisor audit.
- Explicit **Evaluate corrected transcript** pins the prior evaluation's published scorecard and corrected speaker revision, queues one QA request, and reuses the stored transcript. **New QA evaluation** can still select the currently active scorecard. Duplicate/concurrent reevaluation requests conflict rather than creating a second job.
- Immutable per-evaluation context records the transcript fingerprint, correction revision, exact source offsets, effective roles, and manual/inferred provenance. The OpenAI adapter receives corrected roles as separate untrusted context alongside the original numbered evidence excerpts. Existing category/schema/score-sum/verbatim-evidence validation is preserved.
- Team & Access at `/team`: Owner/Admin sees organization users and up to 100 recent invitations, invites by email and role, and revokes pending invitations. New invitees create a verified account directly in the existing organization. Existing accounts must authenticate with the matching invited email, have no existing organization, and explicitly accept. Their passwords are never replaced by invitation redemption.
- 48-hour, random, hashed, single-use organization/email/role-bound invitation tokens. Reinviting revokes the previous pending token in that organization. Acceptance is atomic; expired, revoked, used, forged, mismatched-email, or unauthorized-inviter tokens fail closed. No invitation can grant Owner. Joining does not create a business or grant an entitlement.
- Existing mail abstraction reused: TLS SMTP or explicitly enabled private local outbox. Local invitation UI says no email was sent. Links use URL fragments; raw tokens are not returned in management APIs or logs. Delivery failures roll back issuance and log only safe event/error type.
- Dashboard customization: show/hide and reorder four supported modules (organization metrics, processing attention, recent interactions, review queue). Preferences persist per authenticated user in the server database with revision conflict checks. No invented trend/critical-failure data.
- Appearance: Light, Dark, System persisted per user. System reacts to browser preference changes. Shared theme tokens cover panels, tables, transcript, QA, scorecards, uploads, account pages, dialogs, status/error states and forms. Anonymous pages follow the browser until identity is known; signing back in restores the user's saved choice. The approved navy brand rail remains intentional in both modes.

### ARCHITECTURAL FOUNDATION ONLY

- Existing Call/Transcript/Evaluation architecture is the ingestion boundary for future integrations; there is no external integration implementation.
- User roles support access distinctions. Employee records do not yet link to User accounts or implement employee self-service performance visibility.
- Existing development entitlement state and mail adapters remain the production integration boundary; they are not real billing, delivery monitoring, or paid-access infrastructure.

### NOT YET IMPLEMENTED / bounded limitations

- Bulk assignment across selected interactions; assignment currently happens per interaction. No audio fingerprinting beyond exact bytes, chunked resumable browser transfers, distributed workers, cancel/reorder queue controls, or automatic provider retries.
- Duplicate hashes exist for uploads made after this migration, including new single uploads. Old recordings are not re-read/backfilled during migration. The original single-upload endpoint intentionally retains its prior ability to create a separate call; use Bulk upload for duplicate linking.
- Keep the browser open until transfer finishes. Server processing continues after accepted uploads even if navigation/browser closes; unsent files require reselecting the recording. An abandoned transfer lease becomes replaceable after ten minutes. A replacement preserves the original manifest filename while the linked interaction uses the replacement recording's name.
- Demo QA remains explicitly synthetic and may return the same score after a speaker correction. Live evaluation may also legitimately produce an unchanged score. The deterministic regression uses a controlled valid 90→88 result to prove propagation; no live AI requests were made during development.
- Retry after a failed QA request uses the rubric/context pinned for that attempt. If speakers change again during queued/failed/in-flight processing, that result remains outdated; explicitly evaluate the latest corrected transcript after completion. Resetting a speaker correction also creates a new revision and conservatively requires reevaluation.
- Analytics are descriptive current-state summaries, not employee ranking or statistically validated trends. Each eligible interaction has equal weight. Category averages remain separated by immutable scorecard version; overall 100-point averages may span standards and are labeled accordingly. Fewer than five eligible evaluations is a limited sample. Deactivated employees retain prior assignments and their attributable history; they cannot receive new assignments.
- Team UI invites/revokes and lists users; existing-member role editing/deactivation, ownership transfer, multiple organization memberships, employee-user linking, resend jobs, email delivery monitoring and public abuse controls remain future work. To replace/resend an unaccepted invitation, invite the same address again.
- No real billing/checkout, external integrations, native app, live listening/coaching, fabricated customers/analytics, criterion-level critical-failure/N/A redesign, retention deletion, or public deployment.

## Current score and audit rules

The latest persisted successful evaluation is the effective evaluation for a call. Its score includes the existing append-only supervisor category adjustments. It is eligible for current analytics only when its captured transcript revision equals the current speaker-correction revision. Older evaluations and their adjustments never count again. A pending/failed new request does not delete the prior result; if that result is outdated it remains excluded. Assignment determines which employee receives that one current contribution; reassignment removes it from the old employee and adds it to the new, without rewriting QA or transcript records. Unassigned interactions still contribute to organization performance. Review queues include outdated evaluations even if their historical review was marked complete.

## Schema and migrations

Apply through the normal launcher/Alembic; no `create_all` was added to production.

- `f624025ace05` after Part 1 `e513f149bd04`: nullable indexed Call content hash, `upload_batches` and `upload_items`; unique organization/request-key idempotency.
- `g735136bdf06`: `employees`, nullable Call employee FK, assignment revision, `employee_assignments`, requested QA context, and Evaluation transcript revision/context. Existing QA gets revision zero and nullable legacy context; historical payloads are untouched.
- `h846247cef07`: `invitations` (scoped hashed token, lifecycle and acceptance audit) and `user_preferences` (user PK, appearance, ordered modules, revision).
- Downgrades refuse to discard new operational/audit/preference data. Restore a verified backup if rollback is needed after use.
- Rehearsal used a private SQLite backup and checked every original column/value, FK integrity and `alembic check`. Preserved exactly: **2 users, 6 calls, 6 transcripts, 7 evaluations**. Source/live database was not migrated by this run. These counts reflect the current source at rehearsal time, not the older Part 1 snapshot.

## API additions and behavior changes

| Endpoint | Contract |
|---|---|
| POST /batches | 1–100 manifest entries and stable request_key; tenant/entitlement/review required |
| GET /batches; GET /batches/{id} | Scoped persisted item/count/status history; list pages of 20 |
| POST /batches/{id}/items/{id}/upload | One independently validated recording; bounded lease and idempotent binding |
| GET/POST /employees; PUT /employees/{id} | Scoped search/status/pagination and revision-checked employee management |
| GET /employees/{id} | Profile and current attributable performance |
| POST /calls/{id}/assignment; GET /calls/{id}/assignments | Revision-checked assignment and immutable audit |
| GET /calls?employee_id=... | Specific employee or `unassigned`, alongside existing filters |
| POST /calls/{id}/reevaluate | Latest evaluation ID, active or same historical published rubric, optional current transcript revision; captured context |
| GET /calls/{id}; GET /calls/{id}/evaluations | Evaluation context/revision and dynamic stale/current revision metadata; stored result immutable |
| GET /dashboard | Current non-outdated latest totals and performance sample metadata |
| GET /team; POST /invitations; POST /invitations/{id}/revoke | Owner/Admin scoped management; no raw bearer tokens |
| POST /invitations/preview | Bearer-token details only; bounded account limiter |
| POST /invitations/register; POST /invitations/accept | New-account or authenticated existing-account acceptance, atomic consumption |
| GET/PUT /preferences | Current account only, constrained ordered modules/appearance and optimistic revision |

Existing operational permission/entitlement checks, exact Origin and X-Drive-Request requirements, HttpOnly session cookies and authenticated audio remain. Preferences are basic account access and do not grant operational access. The OpenAI structured-output contract still uses `responses.parse` with Pydantic `text_format`, `store=False`, and exact numbered evidence materialization; [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs) was checked for the adapter extension.

## Frontend and implementation map

New routes: `/batches`, `/employees`, `/employees/[id]`, `/team`, `/accept-invitation`. Existing dashboard, call list/detail, upload entry and navigation extended. New components: `batch-upload`, `employee-assignment`, `preferences`. `operations.css` and `appearance.css` cover the new flows and semantic themes. Root PreferenceProvider loads the authenticated user's choice without redirecting anonymous account screens.

Backend additions: `batch_routes`, `employee_routes`, `team_routes`, `preference_routes`; shared `services/ingestion` and `services/performance`. Existing models, auth permission matrix, processing, review routes/schemas, providers, safe QA errors and account-mail subject mapping extended. Transcription adapter and strict QA contract/rubric validators remain unchanged.

## Validation and manual acceptance

Automated results are recorded in SIGNAL-QA.md. New coverage includes ten- and fifty-file processing, invalid items, exact duplicates and retries, idempotency/leases, tenant isolation, employee lifecycle/permissions/reassignment, corrected score propagation without retranscription, pinned retry context, fingerprint mismatch, provider role attribution, secure invitations and independent preferences. Browser tests use isolated demo servers and temporary databases/outbox, never the live data.

1. Stop the old launcher with Ctrl+C and run `Start-Signal.ps1`. It applies all pending migrations before starting services. No new dependencies or environment edits are required. Existing credentials/providers remain intact; renew development access only if the existing seven-day grant expired.
2. Open Bulk upload. Select ten WAV/MP3/M4A recordings plus an invalid file, submit, and keep the tab open until transfer ends. Verify independent outcomes. Navigate away/return. Retry just a failed item. Repeat the same exact file to verify linking rather than another processing request. Fifty-file backend coverage is automated; live bulk processing incurs normal provider costs.
3. Open Employees as Owner/Admin/Manager. Create a tracked employee, open an interaction, assign it and open its profile. Reassign/unassign and inspect Assignment history and both profiles. Use the employee filter in Interactions. Deactivate/reactivate without losing historical data.
4. Correct a turn's speaker role. Verify OUTDATED SCORE and exclusion from current aggregates. Choose Evaluate corrected transcript, review the scorecard/request confirmation, and start. Confirm current score and profile update and both evaluations remain in history. No transcription request occurs. Stored-transcript Retry remains available for existing failed calls.
5. Open Team & Access as Owner/Admin, invite Manager/Reviewer/Admin/Employee. In local mode open the newest private `backend/data/mail-outbox` invitation file (or configured MAIL_OUTBOX_DIR) and use its full link in a separate browser session. Create the invited account or choose Sign in to accept. Confirm existing organization membership and role permissions. Never share outbox files/tokens or package them.
6. Customize dashboard visibility and order; save, refresh, sign out/in. Verify another user's settings remain independent. Switch Light/Dark/System; change browser system preference and confirm System follows it. Appearance is also available on account screens and mobile navigation.

## Next milestone

Harden public operations before launch: billing/entitlement source, real mail delivery/retry monitoring, shared rate limits, durable scalable worker infrastructure, retention policy, usage accounting and operational observability. Product follow-ups: bulk employee assignment, existing-user access editing, employee-user linkage/self-service, controlled QA eval datasets and transparent version-aware trends. Preserve the working current-score/audit chain.

---

## Historical Day 2 Part 1 handoff


## Current delivery boundary

Day 2's **customer-entry milestone** is implemented on the Day 1 foundation. This is a coherent local journey, not completion of the entire Day 2 commercial-product request. Continue with employees/assignment and bulk ingestion next; do not rebuild authentication or review controls.

Working now:
- Browser registration with name, normalized work email, password validation and Argon2 hashing; duplicate and invalid-input handling.
- One-use verification (one hour) and password-reset (30 minutes) links; resend replaces prior links. Reset revokes every session for that account. Tokens are hashed in the database and never returned by public APIs or written to logs.
- Account access before organization membership. A verified user creates a new organization atomically and becomes its Owner. Guessed tenant IDs and public role assignment are rejected.
- Tenant-owned initial 100-point Dispatch QA starter; duplicate/customize through the existing immutable version workflow.
- Shared operational access gate across all existing operational APIs and the worker. No organization receives automatic operational access. Access is checked before transcription and again immediately before QA. A blocked job becomes retryable failed work; committed transcripts and historical QA remain.
- Inactive/trialing/active/past_due/canceled state semantics, source and expiration fields, and audited seven-day development activation by Owner/Admin. Only an enabled, unexpired development source currently grants access; unknown/payment-looking sources fail closed.
- Account/access screen, persistent setup guide, skip-for-now and completion, existing scorecard/single-upload/review journey, and existing-account login routing.
- Explicit local outbox and TLS SMTP mail adapters. Local mode states that no email was sent. Disabled delivery reports configuration required.
- Responsive Zoqari account/setup screens using existing approved assets and fonts. Credential forms stay disabled before JavaScript is ready and use POST as a native fallback, preventing accidental credential-bearing GET submissions.

Foundation only / not implemented:
- There is **no real checkout or billing integration**, paid activation, usage quota/accounting, invoice system, or production entitlement source. Production cannot use development activation or local mail.
- Employee/agent is a permission concept only. Employee profiles, invitations, employee assignment/reassignment history and self-service employee views are not implemented.
- Bulk upload/manifests/idempotency, generalized interaction source metadata, employee/team SignalScore trends, expanded analytics and coaching pages remain the next Day 2 continuation.
- Existing QA strengths/coaching suggestions remain available per evaluation. No new coaching product, critical-failure/N/A scoring, integration, mobile app, live guidance or AI agent was built.
- No public deployment/readiness claim. SMTP transport is unit-tested with a mock, not a live mail-service delivery test. Public launch still needs delivery monitoring/retries, shared rate limiting, security/privacy review, billing and infrastructure work.

## Restart and use locally

The existing private backend environment was extended with **ENVIRONMENT=development**, **MAIL_DELIVERY=local**, and **DEV_ENTITLEMENTS_ENABLED=true**. Existing provider settings, credentials and trusted localhost origin were preserved. Defaults in Settings remain disabled for mail/development grants; the example environment explicitly enables the local workflow.

1. Stop the existing launcher with Ctrl+C, then run **Start-Signal.ps1** from this project. It migrates before starting services and no longer prompts for a command-line first administrator. No dependency changes are required for this milestone.
2. Open **http://localhost:3000**. Existing credentials still work. The migrated organization starts inactive; sign in and select **Activate development access** once. This is a seven-day test grant, not a payment. It does not switch live AI providers to demo or cover their costs.
3. For a new customer, select **Create an account**. Open the newest verification message in **backend/data/mail-outbox** using File Explorer, then open its link in the same browser. These private files contain credentials: never serve, commit or share them. A custom MAIL_OUTBOX_DIR changes that operator location.
4. Confirm verification, create the business, activate development access, and continue setup. Review/customize the scorecard, upload a recording, and review its transcript/evaluation. Finish setup or choose to finish later; the guide remains in navigation.
5. Forgot-password follows the same local outbox workflow. Use the reset link, choose a new password, then sign in again. Verification and reset links are separate and cannot substitute for each other.

Existing migrated users are treated as previously trusted, operator-provisioned accounts and are marked verified for compatibility; this does not claim that an email verification was previously delivered. Existing organizations have setup dismissed to avoid forcing repeat onboarding. New accounts start unverified with no organization; new organizations start inactive with setup unfinished.

The **live database was not migrated during development**. Only private copies and temporary test databases were migrated. Restart applies the tested migration. No recordings, transcripts, original QA, review edits or passwords were deleted or rewritten. Existing failed calls can still use **Retry** after access is activated; saved transcription is reused without another transcription request.

## API and role contract

Existing API paths/cookie/header names remain for compatibility. Authentication, exact-origin and X-Drive-Request checks remain in force.

| New route | Purpose / authorization |
|---|---|
| GET /auth/options | Public delivery-mode/registration availability; no secrets |
| POST /auth/register | Public registration; no organization/role input |
| POST /auth/verification | Signed-in account resends its own verification |
| POST /auth/verify-email | Consume verification token |
| POST /auth/forgot-password | Generic response for matching/nonmatching accounts |
| POST /auth/reset-password | Consume reset token, change hash, revoke all account sessions |
| POST /organizations | Verified account with no existing organization; creates Owner and starter scorecard atomically |
| GET /account | Signed-in basic profile, access state, setup and capability flags |
| POST /subscription/development-activation | Verified Owner/Admin in explicitly enabled local development; selects tenant from session |
| GET /onboarding | Entitled review-capable user, tenant-specific upload progress |
| POST /onboarding/complete | Entitled Owner/Admin; requires an upload unless skip=true |

OWNER and ADMIN manage tenant users/scorecards and review interactions. MANAGER, REVIEWER and legacy SUPERVISOR can review but cannot manage scorecards/users or activate access. EMPLOYEE has basic account access only until an explicitly scoped employee-view implementation exists. Public signup cannot choose roles; /users cannot assign OWNER. The trusted local CLI remains an operator tool; newly provisioned accounts must verify through the account screen.

All operational endpoints run the same verified/membership/entitlement check before their role check. Account/auth/logout routes remain usable without entitlement. Disabling development access, expiry, inactive, past_due and canceled states block reads, uploads, retries, review edits and background provider requests. An already in-flight provider request cannot be recalled; access is rechecked before the next paid stage.

## Configuration and security

New settings: ENVIRONMENT (development/production), DEV_ENTITLEMENTS_ENABLED (false by default), MAIL_DELIVERY (disabled/local/smtp), MAIL_OUTBOX_DIR (./data/mail-outbox), SMTP_HOST, SMTP_PORT (587), SMTP_USERNAME, SMTP_PASSWORD, MAIL_FROM.

Local mail and development activation require both development environment and a loopback frontend origin. Production configuration rejects either development feature, requires HTTPS frontend origin, secure cookies and SMTP configuration. There is deliberately no API accepting a client-reported paid status. Production operations remain unavailable until a real verified billing source is implemented.

SMTP uses STARTTLS with certificate verification. Tokens use 32 random bytes and SHA-256 storage; token redemption is atomic and tested concurrently. Link secrets live in URL fragments, which are not sent in request URLs or Referer headers. Successful consumption clears the fragment. Local outbox files use restrictive creation permissions where supported and are excluded by data-directory packaging rules. Mail exceptions log their class only, not recipient, token, body, credentials or provider exception text.

A bounded per-process account limiter allows 20 requests/hour/IP across registration, verification and recovery. Existing sign-in limiting remains. This is appropriate to the current one-process local architecture; deploy a shared/edge limiter and durable mail delivery before public rollout. Recovery returns the same content for unknown accounts and delivery failures; real SMTP timing has not been hardened against account-existence inference.

## Data, scoring and migrations

Migration **e513f149bd04_customer_entry.py** makes user organization nullable for account setup, adds verified state and organization access/setup fields, and creates hashed account tokens and entitlement audit events. Original Call/Transcript/Evaluation schemas and contents remain intact. Downgrade refuses to discard new account/access data.

Rehearsal helper: from backend run **..\\.venv\\Scripts\\python.exe -m tools.rehearse_customer_entry**. It takes a SQLite online backup under ignored data/rehearsals, migrates only that copy, compares every original column/row, checks foreign keys and runs Alembic schema check. Current source snapshot: **1 user, 5 calls, 5 transcripts, 4 QA evaluations**, all preserved exactly, along with all other original tables. Source database unchanged.

SignalScore math is unchanged: category final scores use the latest effective audited override or original AI score; their bounded total is the interaction score. The dashboard averages each interaction's latest evaluation once. Historical scorecard maxima remain fixed. No employee/team aggregate, sample-confidence claim or critical-failure metric is introduced in this milestone.

## Changed files and verification

New backend modules: account_routes.py, account_schemas.py, services/account_mail.py, services/entitlements.py; new migration, tests/test_customer_entry.py and tools/rehearse_customer_entry.py.
Updated backend modules: models.py, config.py, auth.py, main.py, services/processing.py, services/rubric.py; test fixtures, e2e_server.py, tenant fixture; .env.example. The successful transcription and QA provider implementations are unchanged.

Frontend: new register/verify-email/forgot-password/reset-password/account/onboarding routes, account-frame/account-form components, account.css and use-hydrated hook. Updated login, shell, role-aware scorecard controls, API types, layout, Playwright configuration and workflow tests. Start-Drive.ps1 removes forced CLI signup; Start-Signal.ps1 remains its wrapper.

Validation results are recorded in SIGNAL-QA.md. Backend baseline was 96; new customer-entry suite adds 39 cases including isolation, permissions, expiry, worker gates, concurrent redemption, token lifecycle, reset session revocation, redacted failure logs and TLS transport. Browser coverage adds the complete customer journey, recovery and pre-hydration form protection. Temporary demo providers only; no live OpenAI or SMTP requests.

## Next continuation

1. Implement tenant-owned employee profiles, activation/deactivation and interaction assignment with append-only attribution history; add two-tenant and historical-preservation tests.
2. Add durable bulk ingestion with per-file validation/outcomes, source metadata and idempotency, reusing the existing queue and entitlement checks.
3. Define and test employee/team SignalScore populations, latest-evaluation selection, historical-version handling, exclusions and small-sample messaging. Build dashboard/coaching surfaces only from those real aggregates.
4. Add an actual billing adapter, verified lifecycle events, usage accounting and production mail delivery hardening. Preserve the fail-closed access decision.
5. Preserve all Day 1 review controls. Keep corporate Zoqari files read-only.

---

# Historical Day 1 handoff (superseded above for account entry and next steps)

## Delivered

The original supervisor-controls pass is implemented, with the new Signal brand and organization boundary added after the updated product request. This is the **organization and quality-review foundation milestone**, not the complete commercial Signal v1 release.

- Zoqari Signal interface based on read-only corporate BRAND.md, CSS, approved artwork, and Sora/Inter. New navigation: Overview, Interactions, Upload call, Scorecards. No nonfunctional navigation was added.
- Speaker correction per exact source span, with provider-ID bulk scope and append-only audit; original inference, raw words and prior QA remain unchanged.
- Normalized organization-specific versioned scorecards with draft editing, category order/name/description/weight/criteria, duplicate, archive and explicit publish confirmation. Exactly 100 points required. Published content is immutable.
- Signal Score alongside original AI score, bounded category adjustments with mandatory reasons, server totals, immutable AI results, audit history and reset. Supervisor review completion and review-queue filtering.
- Explicit new evaluation against the captured active scorecard; original evaluations and adjustments remain in history. Saved transcripts are reused.
- Server-side tenant ownership/filtering across existing resources and new review commands. Organization ownership must be explicit for new users/interactions/scorecards. Existing data migrates into one workspace.

## Major changed modules

Backend: `app/models.py`, `auth.py`, `main.py`, `cli.py`, new `review_schemas.py`, `review_routes.py`, `services/reviews.py`, and rubric/QA contract/provider/processing services. The successful OpenAI transcription adapter remains functionally unchanged. The provider abstraction now accepts rubric context.

Migrations: `c301d927fb02_supervisor_controls_and_versioned_.py` and `d402e038ac03_organization_isolation.py`, plus SQLite migration-connection FK handling in `migrations/env.py`.

Frontend: app shell, branding/metadata/icons, dashboard, calls table/filtering, detail, transcript viewer; new scorecard editor, speaker-control, qa-review, dialog components and `app/signal.css`; self-hosted fonts and package lock.

Validation/docs: `tests/test_supervisor_controls.py`, test database fixtures, isolated browser bootstrap and `frontend/tests/workflow.spec.ts`; README, SIGNAL-PLAN, SIGNAL-QA, launcher aliases and this report.

## Validation results

- Backend: **96 passed** (80 existing plus 16 new cases). Ruff passed. Only existing dependency deprecation warnings remain.
- Frontend: ESLint, TypeScript and production build passed.
- Browser: **3 workflows passed**, covering login, upload/process/playback/search, grouping/timestamp seeking/raw view, role correction, override/reset, review completion, scorecard edit/publication, history, logout and mobile reflow. All use temporary synthetic data.
- Alembic schema check: no missing upgrade operations after migrations.
- Migration rehearsal on a private copy of the user's database: **1 user, 4 calls, 4 transcripts, 3 QA evaluations preserved exactly**; foreign-key check passed. The actual database remained unchanged. Private rehearsal data is under ignored `backend/data/` and is excluded from source archives.
- No live OpenAI calls were made for this development pass.

## Restart

Stop the current app launcher using Ctrl+C. From PowerShell:

```powershell
Set-Location 'C:\Users\Thoma\Documents\Codex\2026-09-18\files-pasted-by-the-user-i\outputs\DRIVE'
.\Setup-Signal.ps1
.\Start-Signal.ps1
```

Setup safely installs the added font dependencies without replacing existing environment files. Start applies migrations before starting services. Existing credentials work. No re-upload is necessary. Retry on an existing failed call reuses its stored transcript; a new QA evaluation also uses saved text and may incur only QA provider usage.

The directory and legacy launcher/cookie/header/API names remain compatible intentionally. The visible product identity is Signal. No public deployment or DNS changes were made.

## Exact next continuation

Start with **self-service organization onboarding and employee ownership**, not another redesign or rewrite of the completed review controls. Read README, SIGNAL-PLAN and SIGNAL-QA, then implement organization creation/account verification/recovery and employee profiles/assignment using the existing mandatory organization boundary. Seed a new organization's initial scorecard transactionally; do not reuse the legacy bootstrap organization or allow client-controlled ownership.

Next build durable bulk ingestion (batch manifest, source identifiers, idempotency and per-file outcomes) into the existing queue. After that add criterion-level scorecard behavior and tests, actual-data employee analytics/coaching, usage entitlements and real billing, retention/deletion, and production infrastructure/abuse controls. Mobile consumes the same backend; external integrations/live coaching remain roadmap only.

Limitations are explicit: this milestone has no public sign-up, employee UI, bulk uploads, critical-failure/N/A/threshold math, separate analytics/coaching pages, usage quotas/billing, account deletion/retention controls or integrations area. Current dashboard aggregates are for small datasets, PostgreSQL deployment is not integration-tested, and the worker still supports one backend process. It must not be advertised as a production-ready commercial service yet.
