# Signal QA — product corrections and administrative controls

Final validation, 2026-09-21: **181 backend tests passed**, Ruff passed, frontend ESLint/TypeScript/production build passed. **All 12 browser workflows were verified**: the final full run passed the ten existing workflows plus the scorecard/delete/archive workflow; both new product-control workflows then passed in the targeted rerun after fixing a test that clicked an identically labeled checkbox before navigation completed. Earlier fixture updates adopted the new Scorecard labels and reused an isolated test session to respect the unchanged production sign-in limiter. No final unresolved failures.

## New backend coverage

`tests/test_product_controls.py` adds 16 cases (including role parametrization):

- Explicit normal-versus-manager eligibility; safe designation removal with reports; archived managers excluded from new selection while preserving current reports.
- Two intentionally different published contracts: Greeting/Closing 50/50 versus Verification/Documentation 70/30. Selected single upload pins A before processing; provider receives A, stored evaluation identifies A/version and validates against A. New evaluation of the same transcript receives B, persists B/version/categories and leaves A's full history unchanged; no retranscription.
- A provider ignoring the selected scorecard fails category validation while keeping its transcript. Strict contract validation is preserved.
- Batch scorecard pinning, independent accepted calls, manifest idempotency with changed-scorecard rejection, and safe failure for duplicate bytes under a different scorecard.
- Draft/archived/foreign scorecards rejected for ordinary selection; explicit correction uses its previous archived version; no-published-scorecard config remains readable.
- Owner and Admin call deletion: dependent correction/evaluation/override/assignment records removed, audio unlinked, no FK damage, team/employee/count aggregates updated and every batch link becomes a stable tombstone. Repeated delete is idempotent.
- Audio unlink failure persists cleanup work, immediately excludes inaccessible Call data from current metrics, and succeeds on retry with safe audit metadata.
- Manager/Reviewer/Supervisor/Employee cannot permanently delete or use the new admin archive/audit endpoints. Cross-tenant deletes/archive/audits fail closed.
- Unused employee deletes; current and prior assignment, direct-report, reporting audit and User-link dependencies block; archiving preserves existing QA and attribution.
- Active processing blocks deletion; deleting queued work prevents a later worker claim.
- Migration from the hierarchy revision marks only actual prior reporting targets eligible; relationship and normal employee preserved, FKs and schema check pass.

Existing hierarchy tests now explicitly designate their test managers and expect zero-report eligible managers in lists. Existing scorecard tests expect multiple published versions and explicit archive, while retaining immutability, revisions, tenant isolation and stored-transcript reuse assertions.

## Browser and visual coverage

`tests/zzz-product-controls.spec.ts` adds manager create/edit eligibility and safe unused delete; distinct single/new/bulk scorecards and category/history display; blocked employee deletion followed by archive; typed-confirmation call deletion and surviving batch history. Existing hierarchy, review/correction, account/invitation, bulk, theme and dashboard workflows remain passing. Synthetic screenshots of the destructive confirmation and deleted batch entry were inspected and copied to `outputs/Signal-product-controls-validation`. No real customer recording or transcript is used in test artifacts.

## Data preservation

Private online-backup rehearsal preserved every original column/row: **3 users, 8 calls, 8 transcripts, 10 evaluations**, and all other original records. FK check and Alembic drift check passed. The source database was neither migrated nor reset, and no live provider request or real-record deletion was performed.

Commands: backend `python -m pytest -q --tb=short`, `python -m ruff check app tests migrations`, `python -m tools.rehearse_customer_entry`; frontend `npm run lint`, `npm run typecheck`, `npm run build`, `npx playwright test`, and final targeted `npx playwright test tests/zzz-product-controls.spec.ts`. Existing dependency deprecation and Node color-environment notices remain.

## Historical QA record — hierarchy

# Signal QA — organizational hierarchy

Final verification on 2026-09-20: **165 backend tests passed**. Ruff, frontend ESLint, TypeScript and production build passed. All **10 browser workflows pass**: the full run passed the nine existing workflows, then the new hierarchy workflow passed on its targeted rerun after fixing an ambiguous test locator (recording link versus Open link). No product change was needed for that test failure. Existing dependency deprecation/color-environment notices remain.

- [x] Eight new backend hierarchy tests cover assign/change/remove manager, audit actor/time/old/new IDs, direct-report queries and natural manager designation.
- [x] Self-management, direct/deep cycles and simultaneous reciprocal assignments rejected; revision conflicts preserve prior state.
- [x] Inactive manager retains reports/history/current metrics, unchanged association allowed, new reports rejected.
- [x] Interaction-weighted score regression proves 86.7 from 90/90/80; score overrides honored, stale/superseded evaluations excluded, moves and call reassignment update attribution without rewriting QA history.
- [x] Server-side manager/employee filters, incompatible combinations, no-manager roots, tenant ID manipulation on creation/edit/filters/team/history/link rejected.
- [x] Optional one-to-one same-organization User link audited, unique and revision-checked; Supervisor/Manager cannot link; Manager permissions remain organization-wide.
- [x] Browser creates Sarah, David, John, Maria and Robert; assigns John/Maria→Sarah and Robert→David; processes synthetic recordings and assigns calls; verifies team scores, narrowed interactions, Maria's move to David, both updated teams and visible audit.
- [x] Manager table sorting and desktop light/dark plus 390px mobile render; no page-level horizontal overflow or browser page errors. Screenshots visually inspected. Wide tables scroll inside their panels.
- [x] Migration rehearsal on a private copy preserves every original column/row, including 3 users, 8 calls, 8 transcripts and 10 evaluations; FK integrity and Alembic schema check pass. Source DB unchanged.
- [x] No live transcription or QA charges. No resets, deletions, role changes to real users, or dashboard preference migrations.

Commands: backend `python -m pytest -q`, `python -m ruff check app tests migrations`, `python -m tools.rehearse_customer_entry`; frontend `npm run lint`, `npm run typecheck`, `npm run build`, `npx playwright test`, then `npx playwright test tests/zz-hierarchy.spec.ts` after locator correction.

## Historical QA record — Day 2 Part 2

# Signal QA — Day 2 Part 2 operations

Final verification: **157 backend tests passed**, plus **27 affected backend tests passed** after the final provider-reason/profile-label refinements. Ruff passed across app/tests/migrations. Frontend ESLint and TypeScript passed; production build passed with all new routes. **9 Playwright tests passed** on isolated demo servers. Existing dependency deprecation and Node color-environment notices remain; no final failed checks.

- [x] Ten valid files alongside an invalid manifest item; independently validated, queued, processed and persisted states/counts.
- [x] Fifty distinct valid recordings persisted and processed successfully with normal Call records.
- [x] Exact duplicate bytes reuse one interaction; repeat manifest/item submissions are idempotent; tenant isolation prevents cross-organization linking.
- [x] Malformed upload replacement, bounded active/expired lease, individual QA retry preserving transcription; inactive entitlement blocks batch reads/ingestion.
- [x] Employee create/search/filter/edit/deactivate, optimistic revision conflicts, Owner/Admin/Manager controls, read-only review roles, cross-tenant read/write/assignment isolation.
- [x] Assignment A→B→unassigned moves current score contribution without changing transcript/QA; auditable history and employee/unassigned interaction filtering.
- [x] Speaker correction marks QA outdated, removes current interaction/employee/organization score, and explicit reevaluation appends history with exact correction context.
- [x] Controlled valid score changes from 90 to 88 and propagates once to both employee and organization; no retranscription call, original text/segments/result/adjustments preserved.
- [x] Repeat/stale reevaluation requests conflict. Failed QA preserves the pinned context; later corrections keep that result outdated. Fingerprint mismatch fails before provider with safe diagnostic.
- [x] OpenAI mock captures corrected role context separately from unchanged numbered evidence; refusal, structured output, score arithmetic and fabricated-evidence regressions retained. No live provider request made.
- [x] Invitations store hashed scoped expiring tokens; acceptance creates/joins existing organization, no ownership escalation or extra entitlement, no Employee created implicitly.
- [x] Existing account requires matching authenticated email; token cannot overwrite password. Replacement/revocation/expiry/reuse/forged tokens and unauthorized inviter rejected; tenant management boundaries enforced.
- [x] Local-mail behavior explicit; failed mail issuance rolls back without sensitive logs. SMTP remains adapter-tested, not live-delivery tested.
- [x] Per-user preference persistence and revision checks; forged user keys, unsupported/duplicate modules rejected; settings independent between users and organizations.
- [x] Existing six browser flows still pass: account entry/recovery, protected forms, single upload/playback/review, speaker rendering/mobile, versioned scorecards and supervisor edits.
- [x] New browser flow: ten files plus invalid item → leave/return → employee creation/assignment → corrected transcript QA → historical evaluations → profile.
- [x] New browser flow: dashboard module hide/reorder/save, reload/signout/signin, Dark/Light/System live browser preference changes, mobile width, screenshots.
- [x] New browser flow: invitation UI/local outbox → separate session/new invited account → same organization/Manager permissions → member visible in Team & Access.
- [x] Light employee profile and team access, dark dashboard/batches/review, and mobile review captures visually inspected. New screenshots are synthetic test data only.
- [x] Private-copy migration rehearsal and Alembic schema comparison passed; every original column/row preserved: 2 users, 6 calls, 6 transcripts, 7 evaluations; FK integrity intact. Live source DB unchanged.

New tests: `test_batches.py` (9), `test_employee_performance.py` (5), `test_team_preferences.py` (7), one provider adapter regression, and `z-operations.spec.ts` (3). Updated the existing supervisor speaker-reset assertion to distinguish immutable QA fields from dynamic outdated/revision metadata.

An intermediate browser failure occurred during a development hot reload and another exposed an imprecise select label locator. The final uninterrupted nine-test run passed after an explicit Role label and loaded-state screenshot waits. Full-size capture states were inspected, not just test return codes.

Known untested/deferred scope: real SMTP delivery, live AI score quality/latency/cost at bulk volume, enterprise-scale performance, distributed workers, browser transfer continuation after closure, byte-hash backfill for older recordings, bulk employee assignment, member role-edit UI, real billing and public infrastructure. These are not represented as completed features.

---

## Historical Day 2 Part 1 QA record


Final verification: **135 backend tests passed** (96 preserved + 39 new cases), Ruff passed, frontend ESLint and TypeScript passed, production build passed, **6 Playwright tests passed**. Existing dependency deprecation notices and Node color-environment warnings remain; no failed checks.

- [x] Registration normalization/duplicates/invalid and weak inputs; Argon2, no public role/tenant assignment.
- [x] Verification and reset tokens: hashed, separate purpose, expiration, resend replacement, atomic concurrent one-use redemption; reset revokes all sessions.
- [x] Generic recovery responses, safe mail-failure logging, honest disabled/local delivery, SMTP STARTTLS adapter unit test.
- [x] Verified organization creation with Owner and scoped starter scorecard; existing organization cannot be replaced.
- [x] No operational access before activation; known source, enabled environment and expiry all required; inactive/past_due/canceled denied.
- [x] Owner/Admin vs Manager/Reviewer/Supervisor/Employee permissions; tenant-scoped activation audit and setup progress.
- [x] Worker denies before transcription and before QA. Access expiration after transcription preserves text; retry completes with exactly one transcription request overall.
- [x] Production rejects development activation/local mail; unknown entitlement sources fail closed. No fake checkout.
- [x] Browser registration → local verification → organization → activation → setup → scorecard → upload → QA → persisted completion → login.
- [x] Browser password recovery and pre-JavaScript credential form protection. Existing three review/playback/scorecard/history workflows retained.
- [x] Desktop setup and mobile access screenshots inspected; responsive layout and existing brand retained.
- [x] Migration rehearsal: all original columns/rows preserved, including **1 user, 5 calls, 5 transcripts, 4 QA evaluations**; foreign keys and Alembic schema check passed. Live DB unchanged.
- [x] No live AI/mail calls, private-data deletion, corporate-site edits, DNS changes or public deployment.

Not covered because not implemented in this milestone: employees/assignment, bulk upload, employee/team aggregates, expanded coaching/analytics, real billing/checkout and production mail delivery. SMTP transport is mocked; real delivery was not tested. Full Day 2 scope remains incomplete.

## Historical Day 1 foundation checklist

## Verified in this milestone

- [x] Existing login, session expiry/revocation, CSRF, role checks, and private audio range requests.
- [x] Existing upload validation, queue processing, stored transcript persistence, and manual retry without retranscription.
- [x] Original strict category/evidence/score regression suite retained.
- [x] One-turn role correction, known-ID bulk scope, original inference and raw wording preserved, reset and actor/time history.
- [x] Draft scorecard creation/duplication/edit/reordering/archive; exactly 100 points required for publication.
- [x] Immutable published categories and historical QA; active rubric selected per organization.
- [x] Bounded category adjustments, required reasons, server final totals, immutable AI scores, reset history, stale-edit rejection.
- [x] Review completion and review queue; newest evaluation only in dashboard/library metrics.
- [x] Tenant isolation for library/search/dashboard, original audio/range requests, transcripts, scorecards, QA, history and all new mutations.
- [x] Tenant identity derived from authenticated account; client tenant assignment rejected; new data ownership required.
- [x] Migration from old schema preserves user hashes, calls, text, segments, original QA results/version/timestamps and foreign keys.
- [x] Existing database copy migration preserves 1 user, 4 calls, 4 transcripts and 3 QA evaluations exactly.
- [x] No live provider requests, retranscription of existing audio, corporate-site changes, DNS changes or destructive Git actions.
- [x] Frontend lint, types, production build and isolated browser workflow tests.
- [x] Desktop/mobile screenshot review; fixed transcript overflow during visual inspection.

## Before a public commercial release

- [ ] Self-service organization/account onboarding, verified email, password recovery, invitations and employee access rules.
- [ ] Employee profiles/assignment and actual-data team analytics/coaching.
- [ ] Durable bulk upload/ingestion manifests, source metadata, idempotency and duplicate handling.
- [ ] Criterion-level pass/fail, critical failures, N/A policies and thresholds with fully defined scoring math.
- [ ] Plan/usage entitlements, concurrency-safe quotas, server usage accounting and a real billing adapter.
- [ ] Retention, interaction/account deletion and storage cleanup with auditable policies.
- [ ] PostgreSQL migration/integration tests, isolation review, load tests and scalable dashboard queries.
- [ ] Distributed worker leases, crash/retry policy, rate limits, operational alerts and backup restore rehearsal.
- [ ] TLS, exact origin, secure cookies, CSP review, reverse-proxy limits, shared abuse controls and infrastructure secret management.
- [ ] Native-mobile authentication design and API versioning; reuse existing backend business rules.
- [ ] Independent security/privacy review before accepting other businesses' customer conversations.

Do not mark an unchecked item complete merely because its database field or navigation label exists. Integrations and live coaching remain out of scope.
