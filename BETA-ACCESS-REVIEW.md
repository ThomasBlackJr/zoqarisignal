# ZOQARI SIGNAL — BETA ACCESS REVIEW

October 19, 2026. Current Documents checkout only. No deployment, commit/push, Downloads merge, real email/AI request or existing-database change.

## Current model before this change

Authentication accepted valid credentials, but workspace authorization and the frontend Shell required a verified account, organization, active entitlement and review role together. Missing pilot access redirected users to Account/pending approval and denied nearly every operational read API. Platform Admin exposed pilot approval as an account activation-like step.

## New model

Account identity and product entitlement are separate:
- Active accounts can authenticate independently of organization access. Unverified accounts still complete secure six-digit verification.
- Every active verified account reaches the normal dashboard, including accounts without an organization and Employees.
- Review-capable members can read only their own organization's historical calls and prepare role-authorized team/scorecard settings without Beta.
- Accounts without membership, Employees and members of suspended organizations receive empty dashboard summaries, never another member's organization-wide data.
- Upload, batch creation/upload, transcription/retry, QA re-evaluation and AI coaching generation require the existing organization entitlement **and** the existing role permission. Workers continue checking the same entitlement before transcription and QA.
- Suspension denies organizational resources/product actions while leaving account recovery and a safe dashboard available.

“Beta Access” is the product-facing name for existing organization `pilot` grants. The source/status/expiry and append-only entitlement/account audits are retained. Existing grants, expiration and revocations remain valid; no user-level grant, backfill or grant conversion exists. Existing supported development/Stripe policy paths are retained; production development access remains forbidden. Billing prompts are not introduced.

## Platform Admin workflow

1. Sign in normally → dashboard → Platform administration link.
2. Organization search is the primary list: Organization, Members, Status, Signal Access (BETA / NO ACCESS / existing supported access).
3. Open the organization and inspect owner/members/status.
4. Grant Beta Access → confirmation naming the organization and all current/future members.
5. Select Never or a future UTC date; add an optional note → Grant Access.
6. Change Expiration reuses the same explicit audited grant/renewal operation.
7. Revoke Beta Access removes product access for every member, leaving accounts valid.

Separate platform authority is required server-side for every control. Tenant Owner/Admin is insufficient. Supplied actor/role fields remain forbidden. Optional Beta notes are normalized; omission produces an explicit server-generated audit reason. User-status/recovery management retains its required reason. The trusted CLI retains its required-reason and exact-organization confirmation rules.

The organization list and detail refresh after mutation. There is no individual-user activation step. Pause/resume remains separate and cannot be bypassed by a Beta grant.

## User workflow

Signup → six-digit verification → Continue to Signal → normal dashboard.
No organization: dashboard with a voluntary Join/create organization action.
Organization without Beta: dashboard and normal navigation; Analyze a Call explains the restriction and disables upload. Direct upload/bulk pages remain inside the app with the same explanation.
Organization with Beta + review permission: upload → transcription → QA → existing Call Intelligence.
Employee in a Beta organization: inherits organization access state, but upload and organization-wide review remain unavailable under the existing Employee role.
After a grant/revocation: Check access again, window focus or the 15-second access refresh updates controls. Every API request independently checks current authority; UI polling is not the security boundary.
After expiration/revocation: login/dashboard remain available, historical reads stay tenant/role protected, and new upload/AI is denied.
After membership removal: the next request loses that organization's entitlement and data scope. Dashboard becomes personal/empty; login remains valid.

Verification challenge hashing, 15-minute code expiry, attempt limits, resend limits, password recovery, session security and the recent registration submission fix are preserved.

## Security implications

Default deny applies to product actions, not dashboard entry. Shared account/product checks replace the former all-or-nothing workspace gate. Role permissions and tenant filters are unchanged. A known organization ID, membership in another organization or platform metadata authority does not authorize another organization's recordings.

Product-gated endpoints: POST /calls; POST /calls/{id}/retry; POST /calls/{id}/reevaluate; POST /batches; POST /batches/{id}/items/{id}/upload; POST /briefing/issues/{id}/generate. Existing post-upload/post-provider rechecks and worker checks remain intact.

Historical reads and non-AI manual/team/scorecard operations remain role-authorized after Beta expiration. This is intentional: Beta controls new analysis work. A paused organization still cannot read those resources. Revocation cannot cancel already-started provider work retroactively.

No new membership-transfer/removal API was added. Enforcement is derived directly from current membership; removal is tested through trusted changes to temporary test fixtures. Existing queued calls remain organization assets and are governed by that organization's current entitlement, not a stale user-level grant.

## Files changed

Backend:
- app/auth.py: separate verified dashboard identity, review scope and product-required permissions.
- app/services/entitlements.py: separate workspace identity/membership checks from product entitlement.
- app/main.py: safe dashboard/config for every verified account; product gate upload/retry.
- app/batch_routes.py, app/review_routes.py, app/briefing_routes.py: explicit gates for upload/AI, safe empty personal briefing.
- app/platform_routes.py: Beta metadata, optional audited Beta notes; same protected grant/revoke service.
- tests/test_account_lifecycle.py, test_batches.py, test_briefing.py, test_customer_entry.py, test_pilot_entitlements.py, test_team_preferences.py: update old dashboard-denial expectations while retaining role/tenant and adding product-denial assertions.
- Added tests/test_beta_access.py: 13 cases for no-Beta account/workspace, API denial, all/future-member inheritance, revocation/worker denial, membership removal, roles and expiration.

Frontend:
- lib/api.ts; components/shell.tsx: normal dashboard destination; separate account/product controls and live access refresh.
- app/(workspace)/page.tsx; components/ui.tsx; added components/beta-access.tsx: normal dashboard and clear restricted upload.
- app/(workspace)/calls/[id]/page.tsx; components/qa-review.tsx; components/briefing.tsx: disable new AI actions without product access; analysis/review logic preserved.
- app/account/page.tsx: access status without an account activation dead end.
- app/platform/page.tsx: organization-first list, Beta confirmation, Never/date, renewal/revoke and list refresh.
- app/platform/platform.css: readable organization column with contained horizontal scrolling on narrow screens.
- components/verification-code.tsx: verified users continue to normal dashboard.
- tests/customer-entry.spec.ts, registration-validation.spec.ts, zzzzzzzz-lifecycle.spec.ts, zzzzzzz-pilot.spec.ts: updated journeys retain direct API and role checks.
- This report.

Existing provider transports/configuration, verification service, models, migrations and Call Intelligence processing/extraction logic are preserved. Generated Next type-reference changes are restored after checks.

Final baseline hash verification confirms the private environment, models, every existing migration, verification service and all service implementations other than the intended entitlement gate are unchanged. The scoped diff contains 28 modified files and 3 additions (including this report); generated Next references were restored to their original bytes.

## Migrations

None required or added. Existing organization entitlement/audit schema is sufficient. No migration or grant was applied to the existing local/production database. Test-only databases are disposable and isolated.

## Validation

Full backend suite: **412 passed, 1 optional PostgreSQL integration skipped, 26 dependency/Alembic warnings**. Includes the 13 added Beta cases and existing account/billing/Graph/Resend/verification/registration/Call Intelligence/worker regressions. Tests that formerly expected entitlement-based read/dashboard denial now explicitly expect authorized reads **and** retained product-action denial; role/tenant checks were not removed.

All **22 browser workflows passed** across two fresh-server groups (18 existing regressions plus 3 registration cases and the expanded lifecycle). The lifecycle group was repeated after the mobile table adjustment and passed. It verifies no-Beta login/dashboard, disabled upload and direct API denial, privileged Beta grant, immediate refresh and successful synthetic upload, invitation membership/role behavior, deactivation/reactivation, revocation with retained dashboard access, and audit. Existing recovery, scorecard, upload, review, bulk and Call Intelligence regressions pass. No assertions were removed; old pending/redirect expectations were changed to the requested dashboard model with explicit product-denial checks retained.

Windows Playwright teardown stalls after recorded outcomes; runners were interrupted only after their results. Groups use fresh isolated servers to avoid accumulating the unchanged shared-IP account/sign-in limits across unrelated cases. No limit was increased or disabled. All mail/audio/providers are synthetic/local/mocked in disposable databases.

Ruff, frontend ESLint and TypeScript **passed**. Production build **did not pass**: two attempts compiled and passed TypeScript but failed static generation with Windows `EPERM` while creating directories under `.next/server/app`, including `forgot-password.segments/forgot-password`. The existing single-worker override (`CIRCLE_NODE_TOTAL=2`, installed Next derives one worker) did not resolve this run. No checks were disabled, source build configuration changed or database reset attempted. A successful clean build in the intended deployment environment remains required before release. Browser tests and build were run separately.

## Six-persona final review

| Persona | Experience |
|---|---|
| New user, no Beta | Verify → normal dashboard; see clear restricted analysis and optional organization setup. No payment/pending-approval redirect. |
| New USPack user with Beta | Accept invitation or join through verified identity → dashboard → upload if assigned a review-capable role. |
| Existing USPack user | Normal login/dashboard; organization state controls new analysis. Existing corrections and intelligence remain in place. |
| New employee joining USPack | Inherits Beta immediately via membership; Employee role remains limited. Reviewer/Manager may upload. |
| User leaving USPack | Session still identifies the account, but current membership no longer supplies USPack scope/access. Safe personal dashboard; old organization's APIs denied. |
| Platform Administrator | Normal dashboard plus explicit portal link; organization-first search → grant/expiry/revoke with actor/time/reason audit. No customer impersonation. |

## Explicit answers

1. Can anyone with a valid account log in? **Yes**, active accounts with correct credentials; disabled accounts remain denied. Unverified accounts still verify before workspace entry.
2. Can a no-beta user reach the normal dashboard? **Yes**, without billing/account/pending/Platform Admin redirects.
3. Can a no-beta user upload a call? **No.**
4. Can a beta organization upload calls? **Yes**, through members with existing upload/review permissions.
5. Does beta apply automatically to every organization member? **Yes**, as organization access; roles still limit actions.
6. Does beta automatically apply to future members? **Yes**, no individual grant.
7. Does revoking beta remove upload/AI access for all members? **Yes**, at the next request/worker check.
8. Can users bypass the restriction through the API? **No bypass found**; direct analysis endpoints and workers deny missing/revoked/expired access.
9. Can a normal user grant themselves beta? **No**, separate platform authorization is required.
10. Can Platform Admin grant/revoke beta in a few clicks? **Yes**, organization detail → grant confirmation or revoke; no normal-operation CLI step.

## Remaining issues / limits

- Optional PostgreSQL integration still needs a disposable configured test database; SQLite tests do not certify PostgreSQL behavior.
- The local Windows production static build is blocked by the filesystem error above; implementation is not a deployment approval.
- Live email, AI quality, intended-host HTTPS/storage/backups and deployment acceptance remain separately authorized tasks.
- In-memory rate limits remain single-process and shared by client IP; browser groups use fresh servers, and USPack NAT onboarding needs acceptance.
- Access UI refresh is periodic/on focus/manual; APIs/workers enforce immediately at their next check. In-flight provider work cannot be retroactively canceled.
- No new membership-removal UI, role expansion, billing or commercial-launch feature was added.
- A designated platform-authorized operator is required to use the portal. No authority was granted in the existing database. Local services must load the new source before manual acceptance; this task did not restart the existing application.
- Existing operational instructions referring to the old pilot pending-page journey are historical; this report documents the new beta UX. The protected environment/hosting/backup safeguards in PILOT-DEPLOYMENT.md still apply.

No deployment, real provider calls, existing database change, commit or push. Stop here for approval.

