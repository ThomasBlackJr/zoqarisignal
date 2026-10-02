# Operator, speakers, flags and workflow sprint — 2026-10-01

## Architecture audit and implementation

Existing authoritative paths were retained: `UploadBatch`/`UploadItem` manifests -> shared `ingestion.ingest` -> normal Call queue -> saved Transcript -> strict QA; Employee and EmployeeAssignment for attribution; lossless ConversationService plus append-only SpeakerCorrection; FlagRule -> immutable FlagDetection -> optional FlagNotification; shared Next.js shell, dialogs and review components. No alternate processing pipeline or provider was introduced.

### Upload operator assignment

Single upload accepts optional `employee_id` form data. Batch manifests accept optional `employee_id` and persist it before any file transfer. The searchable picker uses the existing tenant-scoped active employee endpoint; the checked batch option applies the selected operator to each **new** call. Leaving it empty or unchecking it uploads unassigned. Owner/Admin/Manager assignment permission is unchanged; review-only users can upload unassigned.

The ingestion transaction validates tenant, permission and active status under the existing organization mutation lock, assigns before queue visibility, and appends the existing assignment audit. Individual reassignment remains supported and uses the same shared service. Invalid or archived selections fail rather than quietly assigning elsewhere; partial failures and replacement uploads retain the manifest intent. Employee permanent deletion now accounts for pending/historical batch references.

Idempotent manifest retries must retain the original operator, scorecard and files. Duplicate linking does not mutate an existing call's owner or add provider requests; the UI explicitly states this exception and shows the actual owner on each result row. A user can reassign that existing call individually. This sprint implements pre-upload assignment as the cleanest workflow; no bulk overwrite endpoint was added for already-created batches. Existing batches retain individual assignment.

### Speaker identification and QA

Whisper's current `verbose_json` adapter preserves timestamps and any supplied speaker IDs but does not provide diarization in the configured whisper-1 pipeline. No provider/model/environment setting was changed, and no extra AI calls were added. There is no first-speaker/second-speaker assumption.

Existing wording cues classify Agent (internal DISPATCHER) and Customer / Caller, propagating consistently over a real shared provider ID when supplied. The new contextual overlay recognizes a full assigned-name self-introduction, rejects conflicting caller cues or multiple candidate identities, and propagates that evidence only through the same actual ID. Without IDs it applies only to the evidenced turn. Assignment alone never establishes identity, and unreliable full-text alignment does not trigger name inference. Unknown remains unknown. A name is displayed only when the introduction supports it; a manual Agent role alone does not prove a person's name.

The overlay preserves original text, segments, fingerprints and turn boundaries, so existing correction spans still apply. Manual corrections override it; the correction dialog defaults to the actual speaker ID's turns when one exists, and still offers a single-turn scope. Original correction history is untouched.

A concrete QA omission was fixed: the worker previously passed speaker context only when correction revision was nonzero. It now passes the pinned context on initial QA too, including operator metadata, speaker IDs, labels, and authoritative manual roles. The OpenAI adapter treats this metadata as untrusted contextual data, never instructions. Evidence remains exact transcript-derived source IDs; category bounds/maxima/totals and evidence validation are unchanged. QA retries keep their original pinned context and saved transcript. Existing evaluations are not rewritten or automatically re-run after reassignment or this upgrade; use explicit New QA evaluation when a new contextual evaluation is desired.

### Flag pipeline findings and fixes

The existing backend already tokenizes Unicode words, case-folds them, ignores punctuation between phrase tokens, and records multiple exact source offsets. Tests verify straight/curly apostrophes in “I don't know”, words, phrases, boundaries, repeated occurrences and no-match cases. No unsupported claim is made that basic matching was universally broken.

Reproduced defects/gaps:

1. **Stale audit UI:** FlagEvidence fetched an empty list while processing, but its effect depended only on call ID, correction revision and history selection. Processing completion at revision zero did not refetch it. Processing status is now a dependency. A browser regression begins with empty flags and makes a matching result available at completion without reloading the page.
2. **Phrase end timestamp:** A phrase spanning turns used the first turn's end. It now uses the final matched turn's end. Mixed role attribution becomes UNKNOWN rather than attributing the whole phrase to one role. Missing timing remains null; timestamps are turn-level evidence, not invented word timing.
3. **Historical visibility:** editing/disabling a rule intentionally removes older detections from the current-only filter. The audit UI now includes history by default and labels revisions/deleted rules explicitly; the API's current-only semantics and library's current flag filter are retained.
4. **Missing deletion:** Add Flag, Edit, and confirmed Delete are now available. Deletion records a tombstone, disables future matching/notifications, and appends an AdminEvent. The original rule row and every historical detection remain. Deleted rules cannot be edited/re-enabled through PUT. Re-creating the same phrase creates a new rule identity, not a rewrite of old evidence.

New/edited rules apply when calls are subsequently processed or via the existing explicit scan. No automatic historical scan, retranscription or paid reevaluation occurs on save/delete. Scanning now has confirmation explaining scope and configured notification effects. The scan reads saved transcripts, may enqueue new configured alerts, and preserves previous detection snapshots. Disabled/deleted rules cannot submit new pending notifications through the existing worker checks; an already submitted SMTP message cannot be recalled.

### UI/UX review

Reviewed the dashboard, calls, upload/batches, review, employees/team, scorecards, flags, account/preferences and shared controls. Retained existing dashboard configuration, team/employee distinction, settings, empty/error components and branding instead of adding duplicate pages.

Changes: three explicit batch steps, optional searchable operator controls for both upload paths, assignment summary/results column, clearer duplicate and retry wording, consistent Calls / Audits and Dashboard navigation labels, active flag/team links, accessible navigation labels, transcript/QA adjacency with flags below, readable Agent/Caller names, flag loading/history/delete/scan states, honest empty scorecard state, and shared wrapping/focus/responsive form/table improvements. Desktop batch and 390px mobile audit screenshots were inspected; the new workflow test checks document overflow. Existing browser tests cover playback, dashboard preferences, hierarchy, scorecards, review controls and mobile flows.

## Migration and deployment

New revision: `p624025efb15` (parent `o513914dea14`). It adds nullable `upload_batches.employee_id` with a named employee FK and nullable `flag_rules.deleted_at`. Existing rows remain unassigned/not-deleted. SQLite upgrade, preservation, empty downgrade/re-upgrade and populated deletion-history downgrade refusal are tested. SQLAlchemy/Alembic operations use portable types; live PostgreSQL remains unverified because the external test database is still unavailable.

Before using these files with your existing local database: stop backend/worker, back up database and private audio, then from `backend` run:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic current
```

Expect `p624025efb15`, then restart the application. Start-Signal already applies migrations during startup. Do not downgrade once batch intent or deletion tombstones exist; the guard deliberately refuses that loss. Do not migrate a production database in each function startup. Follow the controlled PostgreSQL migration procedure in SIGNAL-HANDOFF, using the new head revision.

**No new environment variables.** Existing `.env`, provider configuration, successful transcription adapter, authentication, storage and deployment guards were not changed. Tests use isolated synthetic fixtures/temporary databases and mocked OpenAI requests; they do not switch the real local application to demo or claim a paid live acceptance run. No customer recordings were retranscribed. Production persistent PostgreSQL/audio/worker requirements from the previous milestone remain unresolved and unchanged.

## Verification

Final validation on the completed implementation:

- Complete backend suite: **275 passed, 2 pre-existing failures, 1 skipped** (50.89 seconds). The skip is the unavailable external PostgreSQL integration database. All 16 new operator/flag/migration regression cases passed; existing speaker-correction, saved-transcript retry, strict QA, tenant, batch and routing tests also ran.
- Complete browser suite: **15 passed, 1 pre-existing timeout**, all 16 test outcomes captured by a temporary per-test reporter outside the repository. Both new sprint tests passed. The scorecard-selection setup and client-navigation URL timing in the new workflow were corrected before this final run. The runner hung during web-server teardown after every test had reported and was interrupted; this is not a clean runner exit and is recorded separately from test outcomes.
- Backend Ruff: passed.
- Frontend ESLint: passed.
- TypeScript `tsc --noEmit`: passed.
- Production `next build`: passed; 21 pages generated, including dynamic audit/employee routes.
- SQLite migration upgrade/preservation, empty downgrade/re-upgrade and populated deletion-history downgrade refusal: passed within the backend suite. Full legacy-to-head migration regression also ran; its existing historical-downgrade assertion remains a known failure.
- Backend deployment-routing tests and browser same-origin API/page/static-asset routing test: passed within the complete suites.
- Desktop batch and mobile audit screenshots inspected; mobile viewport overflow assertion passed.
- Final diff/credential-pattern/runtime-file checks: no actual `.env` files, API keys, customer data, SQLite databases, recordings or generated artifacts added to the diff. Restored build-generated `frontend/next-env.d.ts` to its pre-sprint content.

Commands: project Python `-m pytest -q --tb=short --basetemp=<isolated writable test directory>`, `-m ruff check backend`; frontend `npx playwright test` (isolated 3001/8001 servers), `npm run lint`, `npm run typecheck`, `npm run build`. Temporary test paths were outside the repository under `C:/Users/Thoma/Documents/Codex/signal-sprint-tests`; no real/local application database was modified. OpenAI transport is mocked in tests; no additional paid live API acceptance run was performed. **No remaining sprint-related failing tests.**

Known pre-existing failures retained: backend historical downgrade test conflicts with the audit-preservation guard; employee-edit test sends read-only response fields to a strict input schema. Browser password-recovery test uses an outdated exact reset-link label. No security/data-preservation guard was weakened to make these pass.

## Files changed

- `backend/app/admin_routes.py`
- `backend/app/batch_routes.py`
- `backend/app/employee_routes.py`
- `backend/app/flag_routes.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/services/assignments.py`
- `backend/app/services/flags.py`
- `backend/app/services/ingestion.py`
- `backend/app/services/performance.py`
- `backend/app/services/processing.py`
- `backend/app/services/providers.py`
- `backend/app/services/reviews.py`
- `backend/app/services/speaker_roles.py`
- `backend/migrations/versions/p624025efb15_operator_flags.py`
- `backend/tests/test_operator_sprint.py`
- `backend/tests/test_providers.py`
- `frontend/app/(workspace)/calls/[id]/page.tsx`
- `frontend/app/(workspace)/calls/page.tsx`
- `frontend/app/(workspace)/flagged-terms/page.tsx`
- `frontend/app/(workspace)/upload/page.tsx`
- `frontend/app/globals.css`
- `frontend/components/batch-upload.tsx`
- `frontend/components/flags.tsx`
- `frontend/components/operator-picker.tsx`
- `frontend/components/scorecard-picker.tsx`
- `frontend/components/shell.tsx`
- `frontend/components/speaker-control.tsx`
- `frontend/components/transcript-viewer.tsx`
- `frontend/lib/api.ts`
- `frontend/tests/workflow.spec.ts`
- `frontend/tests/z-operations.spec.ts`
- `frontend/tests/zzz-product-controls.spec.ts`
- `frontend/tests/zzzzzz-operator-sprint.spec.ts`

Documentation: `SIGNAL-HANDOFF.md` and this report. Test artifacts/temp databases remain ignored or outside the repository. No secrets or actual environment files were added; no commit, push, migration of user data, or deployment was performed.
