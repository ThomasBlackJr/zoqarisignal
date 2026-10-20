# Call intelligence upgrade — 2026-10-17

## Delivered behavior

Signal automatically reads the owning organization's registered name when transcribing a new call. No vocabulary setup is required. Owners/Admins can optionally add a preferred name, alternate names, abbreviations, pronunciation spellings and industry terms in Calls / Audits. Supported providers receive a bounded vocabulary prompt. Conservative greeting-context, lexical and phonetic matching produces traceable company-wording annotations. Conversation display uses those annotations; original transcript text and raw segments remain unchanged.

Speaker inference adds service and customer cues, propagates only within real provider speaker identities, and abstains when cues conflict. It never assigns Agent from “Speaker 1” or invents audio speaker identities. Existing source spans, manual corrections, audit history and corrected-context QA re-score behavior are retained.

New processing automatically extracts Customer, Address, Order # and HAWB into tenant-owned structured records. Extraction requires explicit source evidence and abstains on conflicting values. Records include source character spans, segment/timestamp when available, source fingerprint, origin, verification state and revision. Confidence remains unavailable rather than presenting an uncalibrated probability. Every change appends an audit event.

Reviewers can edit, verify or remove attributes. Revision checks reject stale saves. Manual values and removal tombstones survive rechecking/reprocessing. Recheck uses the saved transcript and makes no provider request. Calls recorded before this upgrade can use **Extract saved transcript** to populate attributes without retranscribing audio.

Calls / Audits includes paginated attribute search. Order/HAWB comparisons are exact after case, whitespace and hyphen normalization; customer/address searches allow partial matches. Results show the matched attribute, call date, assigned employee, customer and current QA score when available, with a link to review. Existing recording filters remain available.

Related interactions use shared **verified** Order # or HAWB values on both calls. Names and addresses never create links. Removing a relationship stores an actor-attributed, persistent exclusion in both directions. Search, relationships, updates and history reuse existing review permission and verified-account/entitlement checks, and filter every resource by organization.

## Database and backend

Alembic head: **s957358bec18** (previous head p624025efb15).

| Revision | Change |
| --- | --- |
| q735136fac16 | Nullable organization vocabulary and transcript company-correction provenance |
| r846247adb17 | Current call_attributes plus append-only attribute_events; normalized identifier lookup index |
| s957358bec18 | Actor-attributed related_exclusions with unique canonical call pair |

New call-owned rows cascade through the existing permanent-delete workflow. Downgrades refuse to discard populated provenance/history/exclusions. Existing source transcripts, AI evaluation records and speaker correction spans are preserved. No startup create_all was introduced.

Implementation extends the existing provider protocol, Processor, corrected-conversation service, call detail response and router registration. Deterministic extraction and company context live in separate service modules. The dependency lock now includes Stripe/openpyxl and their dependencies, already required by existing billing/import code but previously omitted from the lock.

The worker derives the conversation cache before acquiring a fresh call write lock. This avoids promoting a stale SQLite savepoint snapshot when concurrent batch ingestion commits. A regression test forces that competing commit and confirms transcription and QA are each called once, with source text and all attribute records preserved.

New endpoints:

- GET/PUT /organization/transcription-vocabulary (existing scorecard-management permission)
- GET /calls/{id}/intelligence
- POST /calls/{id}/intelligence/refresh
- PUT /calls/{id}/attributes/{key}
- GET /calls/{id}/attributes/history
- GET /intelligence/search
- GET /calls/{id}/related
- POST /calls/{id}/related/{other}/exclude

## Frontend

The existing call review screen now includes editable structured attributes, verification, evidence playback, paginated correction history and related calls. The transcript panel exposes company wording provenance and preserves the raw view. Calls / Audits includes attribute search and optional administrator vocabulary. Existing playback, speaker correction, QA review/re-score, assignment and recording search remain intact. Desktop and 390px mobile layouts were inspected from actual browser-test screenshots.

## Validation

Backend final suite: **293 passed, 1 optional PostgreSQL integration skip** (22 dependency/configuration deprecation warnings). **All 17 browser workflows passed.** Ruff, frontend ESLint, TypeScript and production build pass. The browser runner was interrupted only after all successful outcomes were recorded because Windows test-server teardown lingered. New tests cover company defaults/provider prompt support, unrelated phrase rejection, identity-aware role inference, source offsets/timestamps, ambiguity/malformed values, persistence/manual tombstones, revisions, identifier/partial searches and pagination, tenant/permission boundaries, verified-ID relationships/exclusions, deletion cleanup, competing upload commits and the real UI workflow. Existing migration-preservation, account, billing, QA and corrected re-score tests are included in backend regression testing. Browser tests use temporary databases and visibly synthetic providers on ports 3001/8001. No unresolved feature-related test failures remain.

New test files: backend/tests/test_company_context.py, test_intelligence_speakers.py, test_call_attributes.py, test_intelligence_api.py; frontend/tests/call-intelligence.spec.ts. Updated tests: backend conversation migration downgrade expectation, context-aware customer-entry test adapter, and employee edit request fields; frontend password-recovery link selector and hierarchy session reuse. The new browser test cleans up its synthetic calls and shares its isolated session with later non-authentication tests; production rate limits remain unchanged.

## Limitations and provider support

- Extraction is deliberately conservative English rule-based extraction, not universal language/entity recognition. Lowercase/unusual names, international addresses, spelled-out identifiers, multiple conflicting values or absent labels may need reviewer entry. It never selects an arbitrary conflicting candidate.
- The current whisper-1 integration does not supply reliable audio diarization. Unknown roles remain valid, especially for mixed-speaker raw segments and neutral statements without usable identity evidence. This upgrade improves role inference; it does not add an audio separation model.
- Vocabulary prompts are sent only for the supported whisper-1, gpt-4o-transcribe and gpt-4o-mini-transcribe model names. Unknown/diarization model variants skip unsupported prompt parameters. Existing response parsing/provider selection is retained; this change does not certify a new diarization provider.
- Matching similarity is a heuristic, not calibrated confidence. Raw transcript/segments and QA source evidence remain immutable; company annotations are a separate display/provenance layer. New transcriptions store annotations; legacy rows can derive display annotations using current tenant context without a GET write.
- Automatic attributes start unverified. A reviewer must verify shared Order/HAWB values before relationships appear. Optional vocabulary affects future provider transcriptions; it does not trigger retranscription.
- No paid live provider acceptance run or PostgreSQL service provisioning was performed. Tests mock provider requests or use synthetic demo output. The optional real PostgreSQL integration test requires its existing explicit test configuration.

## Configuration and next steps

No new environment variables or mandatory company configuration. Retain the existing provider, account and entitlement configuration. Before using this source with an existing installation, back up the database, install the updated dependency lock, apply the migrations and restart the normal local services. **Migrations have only been run against disposable test databases during this upgrade.** From the backend folder, the migration command is:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
```

For old calls, select Extract saved transcript; new calls extract automatically. Optional vocabulary is under Calls / Audits for Owner/Admin. Verify important identifiers as part of review.

Next: run the existing managed-PostgreSQL rehearsal, evaluate conservative extraction/role quality against an authorized representative corpus, and test any diarization-capable adapter separately before switching providers. Calibrate confidence before exposing probabilities. Load-test tenant search on production-sized data before commercial deployment.

No deployment, Git push, live database migration, customer audio modification, .env change or corporate-site change was performed.
