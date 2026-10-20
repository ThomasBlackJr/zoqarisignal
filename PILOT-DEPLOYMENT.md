# Controlled free USPack pilot: operator and deployment runbook

This is a free, approved pilot, not a commercial launch. It implements the free-access item from the October 19 USPACK-PILOT-READINESS audit; it does not certify a deployed service, live mail/AI quality, or PostgreSQL acceptance. Do not merge Downloads or use its Platform Admin. No Microsoft 365 or DNS changes are part of this implementation.

## Pilot policy and operator boundary

Account lifecycle update: see [ACCOUNT-LIFECYCLE-REVIEW.md](ACCOUNT-LIFECYCLE-REVIEW.md). The current Documents implementation now has a separate, authenticated `/platform` portal; no Downloads code was merged. Normal approval/revocation happens there, with the signed-in platform operator as actor and a required reason. Tenant Owner/Admin roles alone never authorize these endpoints. The CLI described below remains a trusted-server fallback, not the normal account workflow. Organization suspension also denies API and worker access.

After the new lifecycle migration and normal registration/email verification of the designated Zoqari operator, bootstrap that existing account once from the backend directory with the intended protected environment loaded:

```powershell
..\.venv\Scripts\python.exe -m app.platform_cli '<VERIFIED_ZOQARI_OPERATOR_EMAIL>' --reason 'Designated pilot operator bootstrap'
```

This does not create or verify an account or change its tenant role. It revokes sessions; sign in again, then open `/platform`. Search the USPack organization, confirm its owner, enter a reason and optional expiration, and approve free pilot access. Renew/change expiry with another approval; revoke using the separate revoke control. All successful mutations append audit history. Revoke operator authority using the same trusted command with `--revoke`. No operator was bootstrapped outside isolated tests.

Organizations remain denied by default. A trusted server operator can explicitly set one organization's entitlement source to `pilot`, status to `active`, and optional expiration. APIs and the processing worker share `operational_access`; the worker rechecks before transcription and before QA. A missing expiration is permitted only for explicitly granted pilot access, never as a new Stripe/development exemption. NaN/infinite/past expirations are denied. A pilot with an inactive status is denied. Development flags remain forbidden in production.

Grant/revoke requires an existing organization ID, an exact matching organization name, a reason (1–500 characters), and an existing Owner/Admin of that organization for audit attribution. Grants additionally require that account to be active and verified. **The actor email is attribution, not authentication of the terminal operator.** Server/database access is the privileged authorization boundary; give the command only to trusted operators. Ordinary users, Owners and Admins cannot grant themselves pilot access through an HTTP endpoint. A company name, email domain, registration or organization creation never grants access automatically. There is no global pilot switch.

Every grant/renewal and revocation appends an `entitlement_events` record with actor, organization, action, time, expiration and reason. No prior audit is overwritten. For emergency revocation, the audited Owner/Admin may be inactive or unverified: the trusted server operator must be able to reduce access without reactivating a disabled account. That exception never permits a grant. The CLI refuses to overwrite Stripe or unknown entitlement sources. It does not create users, verify email, change roles/membership, call providers, start workers or run migrations. It can replace a local development entitlement for an explicitly approved organization. Treat database operator credentials as privileged; the CLI is not a remote admin portal.

Revocation takes effect on the next operational request/check, while sign-in/account/recovery remain available. Already-started HTTP/provider requests cannot be canceled retroactively. If revoked/expired during transcription, saved transcription is preserved and the next QA access check denies further provider work. Regrant plus an explicit Retry can resume; there are no automatic paid retries. A currently running QA request may finish. Keep the pilot supervised and revoke at the edge as well if immediate incident containment is required.

Permissions remain unchanged: Owner/Admin manage tenant users and scorecards; Reviewer/Manager/legacy Supervisor can review/upload; Employee has account-only access. Review roles see organization-wide data. One USPack Owner should create the organization; colleagues should join through invitations before creating their own separate organizations. Employee tracking records are separate from login Users. Human review remains necessary; Whisper role inference is not true diarization, and extraction is conservative.

## Grant, expiry and revoke

First migrate the intended database, then register and verify the designated Owner through normal email and have that user create the USPack organization. The Account screen explains that approval is pending and hides database IDs. Use Platform Admin for ordinary approval. For the emergency CLI below, a trusted operator must obtain the ID privately, confirming exact organization name and verified Owner email with the pilot sponsor. No live account/grant has been created by implementation tests.

From the **Documents backend directory**, with its intended environment/database configuration already loaded:

```powershell
Set-Location 'C:\Users\Thoma\Documents\zoqarisignal\backend'
..\.venv\Scripts\python.exe -m app.pilot_cli grant --organization-id '<USPACK_ORGANIZATION_ID>' --confirm-name 'USPack' --actor-email '<VERIFIED_OWNER_EMAIL>' --reason 'Approved controlled USPack free pilot' --expires-at '2026-11-19T23:59:59Z'
```

The timestamp above is an example pilot end date, not a promised duration. Choose the approved future date; timezone is required. Re-run grant with a new reason/date to renew. To grant with no automatic expiry, deliberately omit `--expires-at`; a dated grant is recommended. The command confirms the name exactly, so use the real stored spelling if it is not `USPack`.

```powershell
..\.venv\Scripts\python.exe -m app.pilot_cli revoke --organization-id '<USPACK_ORGANIZATION_ID>' --confirm-name 'USPack' --actor-email '<VERIFIED_OWNER_EMAIL>' --reason 'USPack pilot ended or access withdrawn'
```

Revocation retains the pilot source, previous expiry and historical data but sets operational status inactive. It does not revoke an unrelated paid entitlement or delete calls. A later explicit grant restores access. Platform Admin displays the latest audit entries; full history remains in the database. All HTTP administration endpoints require separate platform authority.

On the proposed Linux host, the protected environment file lives outside the release. Run from `/opt/zoqari-signal/current/backend` using the service account and load that file without printing its contents:

```bash
sudo -u signal ../.venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('/etc/zoqari-signal/backend.env', override=True); from app.pilot_cli import main; main()" grant --organization-id '<USPACK_ORGANIZATION_ID>' --confirm-name 'USPack' --actor-email '<VERIFIED_OWNER_EMAIL>' --reason 'Approved controlled USPack free pilot' --expires-at '2026-11-19T23:59:59Z'
# Revoke: use the same command with action revoke and omit --expires-at.
```

Do not run a local command against a remote database until its target has been privately verified. Commands use IDs/emails/reasons, never database passwords, API keys or session tokens as arguments.

## Schema and migration

Current head is now `u179570dfe20`, after `t068469cfd19`. The lifecycle migration adds organization suspension, nullable user creation/last-login timestamps, separate platform authority and account audit tables. Existing users retain unknown historical timestamps; no users gain platform authority or pilot access automatically. Its downgrade refuses to discard recorded lifecycle history. Apply neither migration to the intended database until deployment approval and backup.

New migration: `t068469cfd19`, following `s957358bec18`. It makes `entitlement_events.expires_at` nullable and adds nullable `reason` (500 characters). Existing development events keep their values and NULL reasons. No organization, user, call or Call Intelligence schema/data is rewritten or granted access. All older migrations are unchanged. A downgrade refuses to discard populated pilot audit information. Never downgrade or delete history as a rollback shortcut.

Apply only in the approved target environment, after backup and while application writers are stopped:

```bash
# backend directory, protected DATABASE_URL already loaded
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic current
../.venv/bin/python -m alembic check
```

Windows equivalents use `..\.venv\Scripts\python.exe`. Implementation runs migrations only against disposable test databases. The current local production-like database has not been migrated by this task.

## Hosting architecture

Use one supervised Linux VM/host with an HTTPS reverse proxy, one production Next.js Node process, **exactly one FastAPI process with the existing in-process worker enabled**, managed PostgreSQL and a durable private audio volume. This matches current code without an object-storage or worker redesign. Use a US region appropriate to the approved pilot data policy. Managed service/serverless ephemeral disks are unsuitable as the only audio copy. The current backend explicitly rejects Vercel because persistent audio and long-running processing are not supported there. Do not use multiple Uvicorn workers, autoscaling or overlapping rolling backend releases.

Ports 3000 and 8000 should listen on loopback for this same-host design; PostgreSQL is privately reachable only by authorized runtime/migration/backup clients. The edge exposes HTTPS 443 and HTTP 80 for certificate validation/redirects. No public raw audio directory, database port, secrets file or raw backend port. The database stores a generated audio filename; the worker and API require the same filesystem mount. Use a dedicated unprivileged service account and encrypted durable storage owned by that account. Monitor capacity; neither the filesystem nor provider spending has a complete organization quota yet.

Route browser `/api/*` to FastAPI with `/api` stripped at the edge. All other application paths go to Next. This preserves same-origin cookie/CSRF behavior without broad credentialed CORS. Next's existing internal rewrite remains available, but bypassing that extra proxy for browser API traffic makes client-IP trust and limits easier to validate. Keep `BACKEND_URL` correct at frontend build and runtime. Preserve Cookie/Set-Cookie, Origin, X-Drive-Request and Range; never cache authenticated API/audio responses. See [Next self-hosting](https://nextjs.org/docs/app/guides/self-hosting) and [Uvicorn forwarding settings](https://uvicorn.dev/settings/).

## PostgreSQL and filesystem preparation

1. Provision a supported managed PostgreSQL instance with encrypted storage, private/firewalled access, provider-supported TLS and automated backups/PITR. Create database `signal`, a migration owner and a least-privilege runtime login. Obtain direct migration/test and runtime URLs as required by the provider. Preserve its TLS/CA options; use certificate/hostname verification when supported. Signal normalizes PostgreSQL URLs to psycopg 3 but does not itself enforce TLS.
2. The migration owner must own/create/alter the target schema/tables/indexes/sequences. After migrations, grant the runtime role CONNECT, schema USAGE, required table SELECT/INSERT/UPDATE/DELETE and sequence USAGE/SELECT; set default privileges as the migration owner for later objects. Do not grant runtime superuser/DDL. Use a separate backup role/managed backup facility. Rehearse all roles in staging.
3. Mount durable encrypted storage at `/var/lib/zoqari-signal/audio`. As an administrator, create the service account and private directory, e.g. `sudo install -d -o signal -g signal -m 0700 /var/lib/zoqari-signal/audio`. Keep it outside the release, Next public tree and proxy document roots. Never deploy a new empty filesystem over existing recordings.
4. Use a disposable PostgreSQL database for integration/migration rehearsal. Privately set `SIGNAL_TEST_POSTGRES_URL` there and run backend tests; these tests create/drop a disposable schema. Do not point them at the pilot database. Run grant/revoke/expiry and cross-tenant/concurrent-upload acceptance on PostgreSQL before external access.

## Complete configuration inventory

Use `backend/.env.production.example` as a **template only**. Do not fill it with real secrets in the repository. Store actual backend values in `/etc/zoqari-signal/backend.env`, root-owned, readable only by the service group (0640), or the equivalent protected hosting secret store. Keep schema-owner credentials in a separate `migration.env`, root-owned and readable only by a distinct maintenance account/group (for example `signal-migrate`), not by the runtime `signal` account. Give both accounts directory traversal and release/venv read/execute access without exposing the other account's secrets. Values must follow dotenv/systemd EnvironmentFile syntax; quote values that require it. Frontend values go in a separate protected frontend environment file/build environment. Do not print these files.

| Backend variable | Pilot value / purpose |
|---|---|
| ENVIRONMENT | production; required explicit setting |
| DATABASE_URL | Secret PostgreSQL psycopg URL with provider TLS; required. Use migration credentials only for maintenance, runtime credentials for services. |
| FRONTEND_ORIGIN | https://signal.zoqari.com exactly, no trailing slash |
| COOKIE_SECURE | true |
| MAIL_DELIVERY | resend |
| RESEND_API_KEY | Real server-only Resend secret, entered privately; never chat/Git/browser |
| RESEND_FROM | AccountManagement@zoqari.com; shared sender is Zoqari Signal <AccountManagement@zoqari.com> |
| TRANSCRIPTION_PROVIDER / QA_PROVIDER | openai / openai, not demo |
| OPENAI_API_KEY | Server-only OpenAI project credential with appropriate model access/budget |
| TRANSCRIPTION_MODEL / QA_MODEL | whisper-1 / gpt-4o-mini; existing supported path. QA_MODEL also serves coaching. |
| UPLOAD_DIR | /var/lib/zoqari-signal/audio; private durable mount |
| WORKER_ENABLED | true in the single backend process |
| DEV_ENTITLEMENTS_ENABLED | false; production validation rejects enabling it |
| SESSION_HOURS | 12 recommended explicit value; supported 1–168 |
| MAX_UPLOAD_MB | 24 recommended explicit value; supported 1–24 MiB/file |
| VERCEL / DRIVE_E2E | Absent/false; no test/serverless mode for the pilot service |

The strict required secrets for this architecture are PostgreSQL credentials, RESEND_API_KEY and OPENAI_API_KEY. Default models, size and session settings could be omitted, but explicit values avoid accidental local/demo behavior. No session-signing/JWT secret is needed for current database-backed opaque sessions. Pilot approval is a database grant, not an environment switch.

Frontend: `NODE_ENV=production`, `BACKEND_URL=http://127.0.0.1:8000` for this same-host design, available at build and runtime. Keep provider/database secrets out of `NEXT_PUBLIC_*`. Frontend production output is generated by the lockfile-controlled build, not `next dev`.

Unused conditional variables: MAIL_OUTBOX_DIR is development-only; SMTP_HOST/SMTP_PORT/SMTP_USERNAME/SMTP_PASSWORD/MAIL_FROM are only for SMTP; M365_TENANT_ID/M365_CLIENT_ID/M365_CLIENT_SECRET/M365_SENDER are only for Graph. Preserve Graph support but do not select it or change Microsoft 365 for this pilot. STRIPE_SECRET_KEY/STRIPE_WEBHOOK_SECRET/STRIPE_PRICE_{STARTER,BUSINESS,PRO}_{MONTH,YEAR} stay unconfigured. STRIPE_MODE may retain its unused default test value. No payment method or Stripe account is needed for pilot grants.

## Release preparation and startup

No deployment commands have been executed. The following is a proposed host layout and procedure, requiring separate deployment authorization and actual host details.

1. Transfer an approved source artifact from Documents to `/opt/zoqari-signal/releases/<RELEASE_ID>` using the protected deployment channel. Exclude `.git`, `.env*` containing secrets, `.venv`, `node_modules`, `.next*`, data/audio, outboxes, test results and caches. Keep the example template if desired. Do not copy Downloads or home-PC databases. Record the source artifact checksum; no Git push is required by this plan.
2. Install Python 3.12+, Node.js 22.9+ (a supported pinned runtime), npm, PostgreSQL client tools and Nginx/certificate tooling. In the release: `python3 -m venv .venv`, `.venv/bin/python -m pip install -r backend/requirements.lock.txt`, then frontend `npm ci --no-audit --no-fund`. Supply server-only BACKEND_URL while building. Run full backend tests/Ruff, `npm run lint`, `npm run typecheck`, `npm run build`, and isolated browser tests. A successful clean intended-host build is mandatory; do not deploy around a failing build.
3. Configure protected environment files and service-account ownership. Privately validate production Settings without app/provider initialization, and use `python -m tools.send_test_email` without `--send` for Resend syntax/configuration only. Do not print model Settings, credentials or environment contents. Actual provider authorization/delivery still needs separate explicitly approved acceptance tests.
4. Enter maintenance/admission pause, drain queued/active work, stop existing backend/frontend, take a consistent verified database/audio backup, and migrate using the migration environment. Confirm `u179570dfe20` and `alembic check`. Switch `/opt/zoqari-signal/current` to the validated release atomically while writers remain stopped.
5. Supervise the following commands with systemd (or an equivalent service manager), not an interactive terminal. Backend working directory is `/opt/zoqari-signal/current/backend`; service user is `signal`; protected backend EnvironmentFile is loaded; restart on failure. Command:

```bash
/opt/zoqari-signal/current/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

Frontend working directory is `/opt/zoqari-signal/current/frontend`; load protected frontend environment; run `npm run start -- --port 3000` as `signal`. Ensure the service manager's PATH resolves the pinned Node/npm runtime. Restrict files with UMask=0077, restart on failure and send sanitized logs to the service journal. Use adequate graceful-stop time but **drain work before stop**: current worker shutdown is not a guarantee an in-flight paid request will finish. Starting a second backend runs recovery against the same queue and must be prevented.

If using the CLI or Alembic outside systemd, explicitly load the protected environment; services' EnvironmentFile does not automatically propagate to an operator shell. A safe dotenv loader pattern for migration from the backend directory is:

```bash
sudo -u signal-migrate ../.venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('/etc/zoqari-signal/migration.env', override=True); from alembic.config import main; main()" upgrade head
```

Use the same loader with `current` and `check`. Keep migration credentials out of runtime backend.env. The pilot CLI needs the runtime environment with permission to update organizations and append audit events, not schema-owner credentials.

## DNS, HTTPS and edge routing (future actions only)

Verify ownership and authorization before making DNS changes. `signal.zoqari.com` needs an A record to the edge IPv4 address (or a provider CNAME if using managed ingress). Add AAAA only if IPv6 actually reaches the same secured service. Leave apex/www, Microsoft mail records and existing Resend domain verification records unchanged. Check any existing CAA policy before certificate issuance; do not alter it blindly. This task changes no DNS.

Obtain a valid certificate for signal.zoqari.com and configure automated renewal. One host procedure is to serve only ACME challenges on HTTP first, then use the supported Certbot/Nginx workflow (`sudo certbot --nginx -d signal.zoqari.com --redirect`) after DNS points to the authorized host and Nginx has the matching server_name. Validate renewal with `sudo certbot renew --dry-run`. Do not expose registration over HTTP while waiting for HTTPS.

Example **final** Nginx HTTPS server after certificate issuance (adapt certificate paths and actual trusted topology; validate `nginx -t` before reload):

```nginx
limit_req_zone $binary_remote_addr zone=signal_api:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=signal_connections:10m;

server {
    listen 443 ssl;
    server_name signal.zoqari.com;
    ssl_certificate /etc/letsencrypt/live/signal.zoqari.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/signal.zoqari.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 26m;
    limit_conn signal_connections 20;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy same-origin always;

    # Recommended small-pilot admission barrier. Create per-person credentials
    # locally with htpasswd (interactive prompt), never in Git/chat/URLs.
    auth_basic "USPack controlled Signal pilot";
    auth_basic_user_file /etc/nginx/signal-pilot.htpasswd;

    location /api/ {
        limit_req zone=signal_api burst=30 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache off;
        proxy_read_timeout 180s;
    }
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache off;
        proxy_read_timeout 180s;
    }
}
```

Also redirect HTTP to HTTPS after certificate setup, preserve ACME renewal routing and configure a default server that does not expose the app for arbitrary Host values. A private VPN/IP allowlist can replace the Basic admission barrier where appropriate. Do not use Basic authentication over HTTP. These sample limits require a USPack-network acceptance test: account routes still share 20 requests/hour/IP and login has 10 attempts/5 minutes/IP, including successes. Perimeter rate limits do not remove the application's existing limits or prevent a corporate NAT from sharing one counter. If a CDN is added, validate its trusted-IP chain and overwrite untrusted forwarded headers at the edge; never configure blanket internet trust.

## Health, acceptance and pilot admission

Internal `curl --fail http://127.0.0.1:8000/health` checks database access. `curl --fail http://127.0.0.1:3000/login` checks the frontend. Probe the actual HTTPS route through the admission barrier without putting its password in command history. Confirm Secure/HttpOnly/SameSite=Strict host-only cookies, HTTP redirect, correct Origin, request-verification header, no authenticated caching, 24 MiB upload success/oversize rejection and authenticated ranged playback. No broad CORS is necessary.

`/health` does not prove worker/provider readiness. Monitor service restarts, worker error logs, failed stages and queue age, Resend submission failures, disk usage, database backups and provider budget. Keep private token/code/outbox files and request payloads out of logs. The generic registration response intentionally does not disclose provider delivery failure or account existence.

Before admitting external users, separately authorize real acceptance tests: one registration/code, one invitation and password reset to controlled mailboxes and an authorized representative recording. Check actual inbox receipt, sender/links, verified account/session behavior, transcription/company name, QA, attributes, human speaker corrections and related verified IDs. The implementation tests never send real mail or AI requests. Test from USPack's actual network and with a second organization/unauthenticated browser to verify no call/audio access across tenants. Human review and a recording/PII/retention agreement are prerequisites. No commercial checkout test is required.

## Backups, maintenance and rollback

Define retention, recovery point/time targets, approved recording scope and a named incident/support owner with USPack. Enable managed PostgreSQL backups/PITR and encrypted off-host durable-volume backups. Keep configuration/secrets recoverable through a protected store, not a release archive. A database-only backup cannot restore audio. Coordinate DB/audio checkpoints, pause uploads/writers for a manual consistent checkpoint and retain a manifest of release checksum, migration version and backup time. See [PostgreSQL backup guidance](https://www.postgresql.org/docs/current/backup.html).

For an operator-managed backup, a protected PostgreSQL service file/passfile can supply credentials without URL/password arguments: `pg_dump --dbname='service=signal_backup' --format=custom --file='<PRIVATE_BACKUP_DIR>/signal.dump'`. Snapshot/archive the audio volume during the same checkpoint and transfer both to encrypted off-host storage under restricted credentials. Actual service names/paths/retention and scheduling must be configured on the chosen host. Test restore into a separate PostgreSQL database and private audio volume using `pg_restore --dbname='service=signal_restore_test' '<PRIVATE_BACKUP_DIR>/signal.dump'`, restore corresponding audio and verify users, grants, histories, corrections and playable audio. Do not run restore against the live pilot database. Prevent restores from silently resurrecting recordings intentionally deleted under the retention policy.

Rollback procedure: pause admission/uploads, let work drain, stop services, preserve a fresh DB/audio checkpoint and logs. Prefer switching the current symlink to a validated previous **schema-compatible** release, retaining the expanded audit schema. Never run an automatic downgrade: the new migration refuses to discard populated pilot history. A pre-pilot release does not recognize pilot grants, so rolling back to it denies pilot operations; plan this as an outage and fix forward rather than bypassing the gate. If a full restore is unavoidable, restore the matched database/audio backup in isolation first, obtain approval for its data-loss window, then switch consistently. Verify health, grant/role/isolation behavior and audio before reopening. Do not restore only the DB, overwrite new audio blindly or drop pilot audit rows to force a downgrade.

## Go/no-go checklist

1. Approved release, passing intended-host production build and disposable PostgreSQL rehearsal.
2. Protected real production variables, private persistent storage, HTTPS/edge admission, correct IP/origin/cookies/range behavior and exactly one supervised worker process.
3. Verified DB/audio restore, capacity/queue/mail/provider-cost monitoring, recording policy and support/rollback owner.
4. Explicit live mail/audio acceptance authorization and successful end-to-end results.
5. One registered/verified USPack Owner, one organization, dated approval through Platform Admin, appropriately scoped invitations and confirmation that employees/managers see only the promised data model.
6. Record pilot start/end and usage limits; keep payment credentials and checkout out of scope. Revoke at pilot end or incident.

No deployment, DNS change, live migration, grant, email, AI request, commit or push has been performed by implementing this runbook. A public go-live still requires approval and the checks above.

## Earlier pilot-entitlement verification — superseded by lifecycle report

- Full backend suite: **374 passed, 1 optional PostgreSQL integration skipped**, 26 warnings. Includes existing account, billing, Graph, Resend and Call Intelligence regressions plus 29 new pilot cases: grant/default denial, optional and expired grants, revocation, emergency revocation, production API/worker enforcement (including between AI stages), tenant/role/verification boundaries, safe operator failures, CLI audit and migration preservation/downgrade guards. The skipped PostgreSQL test still needs a disposable service before deployment.
- Full browser suite: **18 workflows passed**, including the real CLI against a disposable database, free-pilot account UI, no payment prompt, no-expiry grant and revocation denial. Existing registration/code/resend/recovery/invitation/upload/review/intelligence workflows pass. The test-only harness exposes a guarded disposable database folder to the CLI test; no production grant endpoint or database seed was added. Windows server teardown stalled; the runner was interrupted only after all 18 successful outcomes were recorded.
- Ruff, frontend ESLint and TypeScript: **passed**. Resend no-send configuration check: **passed**, without contacting Resend. Alembic head is `t068469cfd19`; migration test also passes Alembic schema check on its temporary upgraded database.
- Full production build: **passed with one static-generation worker**. The normal parallel Windows build reproduced the existing EPERM directory-creation error. This installed Next version supports a build-worker environment override; a dedicated PowerShell build session used `$env:CIRCLE_NODE_TOTAL='2'; npm run build` (Next derives one worker by subtracting one). It compiled, type-checked and generated all 21 static pages. No source/configuration edit or disabled checks were used for the workaround. The override was confined to that test process. A clean production build on the intended Linux host remains a deployment acceptance requirement; this local workaround does not certify that host.
- Existing private `.env`, Graph/Resend transports/configuration, Call Intelligence code and pre-existing migrations remain unchanged. No actual pilot grant/revocation or non-test migration was executed.
