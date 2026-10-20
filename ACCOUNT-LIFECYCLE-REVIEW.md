# ZOQARI SIGNAL — ACCOUNT LIFECYCLE REVIEW

Review date: October 19, 2026. Scope: current Documents checkout only. No Downloads merge, live database migration/account/grant, external email/AI request, infrastructure change, deployment, commit or push.

## 1. Current lifecycle before changes

Inspected account/authentication routes, verification and email services, Resend, organization/team routes, entitlement policy and CLI, models/migrations, registration/login/verification/account/onboarding/team/billing UI and tests. Documents had **no Platform Admin implementation** to reuse. No Downloads implementation was imported.

```text
Visitor → Register → six-digit code → Verify → Account → Create organization
       → wait for trusted server operator to grant pilot access → Setup → Workspace
Invitation → create account or sign in → accept one-use email link → existing organization
Login → Account when verification, membership, access or role blocks entry
      → setup/workspace otherwise
Password recovery → one-use reset link → new password → sessions revoked
```

No supported verified-email rename, membership transfer/removal, forced-password-reset state or user/org administration portal existed. Tenant user roles were not platform authority.

## 2. Problems discovered

- An existing verified account registering again received a generic 201 and a fake verification challenge, with no mail. That privacy response looked like a broken delivery flow.
- Verified users without access saw internal IDs, access/entitlement language and billing-oriented context.
- Pilot approval and troubleshooting required privileged terminal/database access.
- Invitations were discoverable only through their email link; ordinary signup could lead invitees toward creating a separate business.
- No account activation/deactivation, organization pause, separate platform authority or searchable lifecycle audit existed.
- Mandatory-looking setup diverted otherwise approved users from the dashboard.
- Email delivery submission and inbox receipt were easy to confuse. Privacy-preserving responses cannot promise delivery or reveal whether an address exists.

## 3. Simplified lifecycle

```text
New signup → six-digit verification → Account
  ├─ pending invitation → Join existing business
  └─ no invitation → Create business → Waiting for approval
Approved + review-capable role → Dashboard (setup guide optional)
Pending/expired/revoked/paused → clear Account explanation + check again
Existing valid credentials entered on signup → sign in → same account destination
Platform operator → separate Platform Admin → search → reasoned, audited action
```

Password recovery remains a separate link flow. Email verification does not grant organization membership or pilot access.

## 4. Changes implemented

Central account destination, plain-language account states, masked verification email, resend/change-email/recovery paths, safe existing-credential sign-in during repeat signup, pending-invitation discovery and identity-bound acceptance, optional setup guide, explicit inactive-account message only after password proof, session revocation on administrative status changes, separate platform authority and lifecycle events, organization suspension and shared API/worker denial.

Existing email templates/transports, six-digit security, tenant permissions and operational Call Intelligence logic are preserved. No global development exemption or fabricated subscription was added.

## 5. Platform Admin improvements

New `/platform` interface and strictly protected `/platform/*` APIs provide:
- Paginated user/org search; name/email, verification/activity, role/membership, creation and last-login timestamps where known.
- Verification resend and existing password-reset initiation, without returning codes/tokens.
- Account activation/deactivation with session invalidation.
- Organization owner/member/access/pilot/expiry/status views.
- Pilot approval/renewal/expiry change/revocation; organization pause/resume.
- Actor/time/reason audit and recent account/pilot history.

All successful privileged mutations append audit records in the same transaction. Failed provider submissions initiated by Platform Admin also receive sanitized audit events. Authorization failures are denied, not represented as successful mutation audits. Historical activity is not reconstructed. The UI shows the latest 50 events and up to 100 org members; full history remains persisted.

Authority is a separate database record, never an OWNER/ADMIN role shortcut. Active verified status and authority are checked server-side. No impersonation, cross-tenant call access, arbitrary verification, password assignment, email rename or membership transfer is offered.

Bootstrap **only after approval, target validation and migration**, from the backend directory:
```powershell
..\.venv\Scripts\python.exe -m app.platform_cli '<EXISTING_VERIFIED_ZOQARI_EMAIL>' --reason 'Designated pilot operator bootstrap'
```
This does not create or verify a user. It revokes sessions; sign in again. Add `--revoke` for trusted-server authority removal. Bootstrap audit attributes the designated account; trusted host access/operator logs are the boundary identifying the terminal operator. Do not delegate this command to customers.

## 6. Free-pilot activation flow

Owner verifies → creates USPack organization → sees waiting-for-approval explanation → authorized platform operator confirms organization/owner, enters reason and optional future expiry, approves → Owner checks access or signs in → workspace.

Default deny, explicit organization approval, optional expiry, revocation, source protection, audit and shared API/worker enforcement remain. Suspension denies access independently of pilot status. Revoke does not delete data or block account recovery. In-flight provider work cannot be retroactively canceled; worker checks prevent subsequent stages. Regrant does not automatically retry failed paid work.

Ordinary Owners/Admins cannot call the approval APIs. Existing trusted pilot CLI remains an emergency fallback. Normal operation no longer requires it.

## 7. Invitation flow

Owner/Admin invites the intended address with an appropriate existing role. Recipient follows the one-use link, creates an account or signs in, accepts and joins the existing organization. The link proves access to the invited mailbox, preserving the prior invitation verification design.

Alternatively, a recipient who registers normally verifies using six digits, then sees invitations bound to their verified identity. Acceptance by invitation ID requires an exact verified email match, valid unused/unexpired invitation and active verified authorized inviter. Other users cannot consume a guessed invitation ID. Existing membership cannot silently be replaced. No duplicate organization is required.

Manager cannot invite login users under current permissions; Owner/Admin must send invitations. Employee is account-only; use Reviewer for call-review access. Manager/Reviewer can access organization-wide reviews, not a private per-employee subset. Employee tracking records and login users remain separate.

## 8. Verification flow

Secure random numeric six-digit code, Argon2 hashed persistence, hashed opaque challenge, 15-minute expiry, five incorrect attempts, persisted 60-second resend cooldown, immediate consumption and previous-code invalidation remain enforced. No plaintext code logging, browser response or admin display was added.

Public wording is deliberately conditional (“If this address needs verification…”), with a masked email, rather than a false delivery guarantee/account-existence disclosure. Resend rotates code and normal anonymous challenge. Admin-assisted resend preserves the already-open challenge while rotating the code; this avoids stranding that verification screen. New browser sessions can sign in and verify via their session.

Change email restarts registration with another address; it does **not** rename an existing account. A verified-email change requires a separate secure design. Existing correct credentials on duplicate signup authenticate normally; wrong credentials neither replace the password nor reveal verified status. Mail submission failures retain generic public responses and sanitized operator logs. The platform cannot inspect an account that was rolled back when initial delivery failed.

## 9. Account-state behavior

| State | Destination / next step |
|---|---|
| Unverified, active | Verify email; cooldown, resend and recovery options |
| Verified, no org, pending invite | Join existing business; creating a separate one is an explicit alternative |
| Verified, no org/invite | Create business |
| Org pending/expired/revoked | Waiting for approval; contact Zoqari/Owner; automatic 15-second state refresh or Check access again |
| Approved, review-capable role | Dashboard directly; setup optional |
| Approved Employee | Clear account-only role explanation; contact Owner for role questions |
| Inactive | Existing sessions invalid; correct password receives inactive/help message; wrong password remains generic |
| Suspended org | Account explains pause; operational API/worker denied |
| No membership | Organization setup/invitations; there is no new removal/transfer endpoint |
| Reset requested | Existing session remains until redemption; redemption revokes all sessions |
| Platform authority | Platform portal; no implicit tenant review privileges |

A sole active Owner cannot be disabled until the organization is paused. Platform operator accounts cannot be disabled through ordinary portal controls, preventing accidental self-lockout; trusted host revocation remains available.

## 10. Security review and second perspective pass

Re-reviewed the completed routes, actor selection, strict mutation bodies, tenant scopes, token/code consumption, sessions, reason requirements and worker gate after implementation, separately from the first design pass. This is a second review pass by the same implementing agent, **not an independent external security audit**.

| Persona | Exact experience and boundary |
|---|---|
| Brand-new USPack employee | Invitation link → choose own credentials/sign in → mailbox proof → join existing org. Employee sees account-only access; Reviewer sees workspace after org approval. No duplicate org needed. |
| USPack manager inviting employee | Manager has no user-invite permission; asks Owner/Admin. Owner/Admin sends role-scoped invite. This role limit is intentional and must be explained in pilot onboarding. |
| Zoqari platform operator | Existing verified account is bootstrapped once by trusted host operator; sign in → Platform Admin → search → inspect state → reason + action → audit. Cannot impersonate or access another org’s recordings. |
| Malicious user | Public signup cannot self-approve, forge actor/role/email fields or reach platform endpoints; invitation identity/replay/expiry and tenant scopes deny escalation. Known organization/call IDs confer no access. |
| No verification email received | Verify screen explains latest-code/cooldown, resend, change-address restart, sign-in and reset. Signed-in unverified users can request again. Zoqari can inspect existing account state and resend; provider logs distinguish submission failures privately. Actual inbox delivery still needs authorized acceptance. |
| Registered but unapproved | Verify → create org → waiting-for-approval explanation, no billing/IDs. Operational APIs deny access. Operator approval plus Check access again/Open workspace completes the journey. |

Regression coverage includes brute force, code/token replay, reset abuse, session invalidation, tenant IDOR, invitation abuse, forged privileged input and unauthorized activation. Correct-password duplicate registration is authentication, not anonymous disclosure. Rate limits remain single-process/in-memory: account routes share 20 requests/hour/IP and login 10/5 minutes/IP, including successes. Perimeter admission and NAT acceptance are essential for USPack. Formal timing side-channel analysis, distributed limiting and MFA are not certified by these tests.

## 11. Files changed

Modified:
- `backend/app/account_routes.py`, `auth.py`, `main.py`, `models.py`, `pilot_cli.py`, `team_routes.py`
- `backend/app/services/entitlements.py`, `verification.py`
- `backend/tests/e2e_server.py`, `test_pilot_entitlements.py`
- `frontend/app/account/page.tsx`, `app/login/page.tsx`
- `frontend/components/account-form.tsx`, `account-frame.tsx`, `shell.tsx`, `verification-code.tsx`
- `frontend/lib/api.ts`
- `frontend/tests/customer-entry.spec.ts`, `zzzzzzz-pilot.spec.ts`
- `PILOT-DEPLOYMENT.md`, `README.md`

Added:
- `backend/app/platform_cli.py`, `platform_routes.py`
- `backend/app/services/account_audit.py`, `pilot.py` (shared existing pilot operation)
- `backend/migrations/versions/u179570dfe20_account_lifecycle.py`
- `backend/tests/test_account_lifecycle.py`
- `frontend/app/platform/page.tsx`, `platform/platform.css`
- `frontend/tests/zzzzzzzz-lifecycle.spec.ts`
- This report.

Final SHA-256 comparison against the pre-change baseline found 21 modified files and 10 additions, exactly as listed above. Generated Next type references were restored byte-for-byte. The existing private environment, account-mail/Graph/Resend services and provider configuration, all pre-existing migrations, and Call Intelligence processing/transcription/QA/extraction code have unchanged hashes.

## 12. Migrations added

`u179570dfe20`, after `t068469cfd19`: adds organization suspension, nullable user creation/last-login timestamps, platform authority and account event tables. Existing users retain NULL historical timestamps; no automatic authority/approval is seeded. New users/session creation record timestamps going forward. Downgrade refuses to discard populated lifecycle history.

Created and tested only against disposable databases. Do not apply to the real database until approved, backed up and writers stopped. Approved-target commands from backend:
```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe -m alembic check
```

## 13. Backend test results

Full final backend suite: **395 passed, 1 skipped, 26 warnings** (177.94 seconds). The skip is the optional disposable PostgreSQL integration test; no PostgreSQL test URL was configured. Warnings are existing dependency/Alembic deprecations. Includes account/billing/Graph/Resend/Call Intelligence regressions, pilot API/worker/isolation tests, and 21 new lifecycle/privilege/bootstrap cases. Migration upgrade and Alembic schema comparison pass on temporary SQLite; this does not replace PostgreSQL acceptance. No live email or AI provider was called.

## 14. Browser test results

All **19 browser workflows passed**, run in two fresh-server groups: all 18 existing regression scenarios, then the new complete lifecycle scenario. Commands: frontend `npx playwright test --grep-invert 'complete free-pilot lifecycle'` and `npx playwright test zzzzzzzz-lifecycle.spec.ts`. Existing scenarios cover recovery, invitations, login, upload/review and Call Intelligence; the new scenario exercises signup/code/pending/portal approval/Employee join/deactivate/reactivate/revoke and correct-password duplicate signup, including a mobile overflow assertion.

The initial combined run exposed stale pilot copy assertions (updated to the final UI) and hit the unchanged shared-IP sign-in limit before the last scenario. Fresh isolated servers avoid cross-scenario limiter state without disabling or increasing production limits. A real mobile member-button overflow was fixed; the new test now waits for selected detail context before editing its required reason. No assertions were removed. A single shared-server run remains susceptible to the real sign-in limit and is not claimed as green.

Windows Playwright server teardown stalls after results; runners were interrupted only after all outcomes were recorded. Tests use disposable migrated SQLite, synthetic identities/recordings, local outbox and demo AI. No production account, authority, pilot grant, external email or AI request was made.

## 15. Ruff/lint/TypeScript/build results

Ruff (`python -m ruff check app tests`), frontend ESLint (`npm run lint`) and TypeScript (`npm run typecheck`) **passed**. Full production build **passed**, including compilation, TypeScript and static generation, using the supported build-worker environment override in a dedicated Windows shell: `$env:CIRCLE_NODE_TOTAL='2'; npm run build` (installed Next derives one worker). No check was disabled or source configuration changed. Normal parallel Windows builds previously reproduced EPERM directory creation failures; they are not claimed as passing. A clean build on the intended Linux deployment host remains required. Browser runs and production build were kept separate. Generated Next type references were restored to their original bytes.

## 16. Remaining issues and acceptance

No live provider receipt, production PostgreSQL acceptance, intended-host release build, actual HTTPS/cookie/edge behavior or backup restoration is certified. No real operator/pilot grant has been created. Follow PILOT-DEPLOYMENT.md; do not deploy on test counts alone.

### Explicit capability answers

| Question | Answer |
|---|---|
| Can a brand-new user register without getting stuck? | Yes in tested success/recovery paths; delivery outages still require support/provider restoration. |
| Can they verify email? | Yes; six-digit signup code or secure invitation mailbox proof. Live inbox acceptance remains outstanding. |
| Can they create an organization? | Yes after verification, when not already a member. |
| Can an approved pilot org immediately use Signal? | Yes for existing review-capable roles, while active/unexpired/not suspended. |
| Can an unapproved org understand why it cannot? | Yes; explicit pending approval/help state, no payment requirement. |
| Can an invitee avoid a duplicate org? | Yes, by email link or verified pending-invitation acceptance. |
| Can Platform Admin manage users? | Yes for state inspection, resend/reset and activation/deactivation; not arbitrary role/email/membership edits. |
| Can Platform Admin approve/revoke pilot? | Yes, with reason, optional expiry and audit. |
| Can Platform Admin troubleshoot account state? | Yes for persisted account/org state and recent audit; failed rolled-back registration/provider inbox state needs sanitized server/provider diagnostics. |
| Are all privileged actions audited? | Yes, successful mutations added here; denied authorization/read-only views are not mutation audits. Trusted host bootstrap attribution has the limitation above. |
| Can a malicious user bypass activation? | No bypass found; targeted tests deny unauthorized/forged activation. This is not proof against every possible attack. |
| Is cross-org data isolated? | Yes under existing tenant authorization, including for platform users; regression tests pass subject to results below. |
| Is the entire flow simple enough to hand to USPack? | Conditionally for a small supported pilot after P0 acceptance and explicit role guidance; not unconditional launch approval. |

### P0 — MUST FIX BEFORE USPACK

- Approve release/migration; rehearse on disposable PostgreSQL, including migration/schema and concurrency/isolation checks. No production test service was available locally.
- Secure intended-host build, HTTPS/cookies/origin/edge admission, private persistent audio, exactly one supervised worker, monitoring and verified DB/audio restore.
- Authorized live registration/code, invitation, reset and representative AI/audio acceptance; verify actual delivery and recording/PII agreement.
- Bootstrap designated verified Zoqari operator, confirm USPack owner/org, dated approval, and assign Reviewer/Manager versus Employee intentionally.
- Rehearse USPack shared-network rate limits; stagger onboarding or approve a separately tested limiter adjustment if current thresholds block legitimate users.

### P1 — FIX DURING PILOT

- Platform MFA/strong identity hardening before widening operator access; keep operator count minimal meanwhile.
- Better mail delivery observability and operational support runbook; submission is not inbox delivery.
- Monitor NAT limits, queue/storage/provider cost and audit retention; distributed limiting before multi-process scale.
- Design secure verified-email changes/membership transfers only if required; current UI intentionally cannot perform them.
- Add pagination/export for full audit/member history beyond small-pilot view limits.

### P2 — FUTURE IMPROVEMENTS

- Role-specific private employee workspace if promised by product policy; current review roles see organization-wide calls.
- Multiple-org membership, delegated operator administration, formal external security/accessibility review.
- Commercial billing, distributed workers/storage and richer historical analytics after the free pilot.

Implementation/testing only. Waiting for approval before any deployment, live migration, real email or account/authority operation.

