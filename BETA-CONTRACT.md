# Signal beta application contract

This reconciles the account/platform merge while retaining every migration in
MIGRATION-RECONCILIATION.md. No additional schema change is required.

## Access

An organization can have an independent, audited beta grant in `beta_access`.
It applies to every member, expires optionally, and does not rewrite billing.
Suspension overrides every grant. Revoking or expiring beta does not cancel a
separate valid subscription, development entitlement, or historical pilot grant.
The existing pilot operator APIs/CLI remain compatible and separately audited.

Accounts without beta approval can sign in and verified tenant members retain
their permitted workspace reads. Upload, retry, reevaluation and AI generation
require valid organization access. An Employee account cannot review other
members' calls or run analysis. Accounts without a workspace or review role see
empty personal dashboard summaries. Suspended accounts cannot read tenant calls;
their basic account page and safe empty dashboard remain available.

The account page returns inactive guidance and effective access expiration,
including independent beta grants. It does not expose secrets or bearer tokens.
Owner billing remains Owner-only. Beta does not imply a paid subscription.

## Platform control

Platform authority is separate from customer membership and roles. Operators
must be active and verified. Grant/revoke through the trusted CLI requires a
reason and always revokes sessions; callers must sign in again. Neither platform
authority nor employee reporting designation grants tenant impersonation.

The shared platform dashboard, organization, user, ownership and activity pages
use the registered platform APIs. There is one handler per method/path. Account
mutations require explicit confirmation, a current administration revision and a
reason. POST status remains a compatibility alias for the same guarded PUT
handler; it is not a weaker alternate implementation.

Owner membership/email changes require a separately confirmed transfer to an
active verified member of the same organization. An Owner may be deactivated
after the organization is suspended; otherwise ownership must be transferred
first. Active platform operators cannot have email/status changed through the
ordinary administration UI. Membership changes remove conflicting employee links
and append history rather than deleting accounts or historical QA.

Platform actions append `platform_events`; account lifecycle and historical
pilot operations retain `account_events` / `entitlement_events`. Trusted authority
changes and platform-triggered pilot changes are also visible in platform audit.
Audit metadata excludes passwords, reset tokens and verification codes.

## Credentials and invitations

Verification issues a one-use six-digit email code with expiry, attempt limits
and server-enforced resend cooldown. Admin resends preserve a pending challenge
while replacing its code. Verification links are not newly issued. Initial admin
account setup sends a reset link and verification code: the recipient chooses a
password, signs in, then verifies with the code. The administrator receives no
credential. Email changes revoke sessions, reset/code credentials and pending
invitations; failed notification delivery rolls back the change. Password-reset
requests do not invalidate a valid session until redemption; successful redemption
revokes all sessions.

Tenant invitations cannot grant Owner or overwrite an existing membership or
password. Platform-issued invitations require current inviter platform authority.
Initial Owner invitations are serialized with organization mutations and cannot
create a second Owner at acceptance. Replacement candidates join as Admin; they
require a separate confirmed ownership transfer. Invitations do not grant beta
access themselves. Acceptance is atomic and one-use, and existing accounts must
authenticate as the invited identity.

## Worker and validation

The worker checks current organization access before transcription and again
before QA. Revocation before work calls neither provider. Revocation during
transcription preserves its committed transcript and blocks QA. No automatic paid
retry is added.

Tests use disposable SQLite/PostgreSQL databases and synthetic providers. Browser
workflows use isolated local servers/outboxes and can use the production Next
build by setting `SIGNAL_E2E_PRODUCTION=1` after building with `DRIVE_E2E=1` and
`BACKEND_URL=http://127.0.0.1:8001`. `SIGNAL_TEST_PYTHON` selects the test runtime.
Run authentication-heavy browser groups against fresh test servers to respect
the unchanged per-IP login limiter. Never point test URLs at production.

Application validation does not inspect or configure the production Droplet,
SMTP/Resend delivery, DNS/TLS, persistent storage, backups or production secrets.


## Validated locally — October 19, 2026

The complete backend suite passes 469 tests with disposable PostgreSQL enabled;
no failures, errors or skipped integration cases remain. Six added regression
cases cover organization beta inheritance/expiration/isolation, worker revocation
and Owner-invitation contention, including application behavior on migrated
SQLite and PostgreSQL. All original test functions and browser scenarios remain.

Twelve affected browser workflows pass against the production Next build in four
isolated groups: onboarding/access/recovery (4), platform administration (3), the
full beta lifecycle including real-clock expiration/renewal/revocation (1), and
operations/team invitation/trusted pilot compatibility (4). Ruff, ESLint,
TypeScript and the production build pass. Desktop/mobile platform captures were
inspected. Login limiting and security-sensitive session revocation are unchanged.

A fresh PostgreSQL 16.6 database upgrades to the preserved single head
`u179570dfe20`, repeats upgrade successfully and passes Alembic drift detection.
All 37 application tables, 301 columns and 73 foreign keys match application
metadata. The existing migration graph regression remains green.

This is application validation for a controlled beta release candidate, not a
certification of an uninspected production host. No production deployment, live
mail/provider request, commit or push was performed.
