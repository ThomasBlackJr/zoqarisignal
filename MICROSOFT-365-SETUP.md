# Microsoft 365 account mail

The focused Graph mail adapter is integrated into the Documents checkout alongside Call Intelligence. Graph authentication and Microsoft 365 Application Access Policy testing were reported successful in the Downloads checkout. This merge is tested with mocked HTTP only: **no external email was sent and no Microsoft 365 configuration was changed**. Actual delivery from this checkout still requires an explicitly approved test. Do not use a personal mailbox or a mailbox password.

## Application and mailbox authorization

1. Have the tenant administrator confirm that `AccountManagement@zoqari.com` is a provisioned Exchange Online mailbox (user or shared), including applicable licensing, sending limits and tenant policy. The application sends through this mailbox and saves sent items.
2. Register a **single-tenant** Microsoft Entra application. Record its Directory/tenant ID and Application/client ID. Create an application client secret in the tenant's approved process; store its **value** in deployment secrets. Record its expiry and rotation owner. Never paste it into source, tickets, chat or logs. This implementation supports client-secret credentials; certificate/federated authentication requires a later adapter enhancement.
3. Use unattended **application** authorization. Delegated Mail.Send and interactive user login are inappropriate for this service. No redirect URI, mailbox password, refresh token, Mail.Read or directory-reading permission is required by this adapter.
4. Prefer **Exchange Online Application RBAC** with the `Application Mail.Send` role scoped solely to the dedicated mailbox. An Exchange administrator must register the application's service principal in Exchange (`New-ServicePrincipal`), using the **Enterprise application service principal object ID**, not the app registration object ID; create a recipient management scope covering only the dedicated mailbox and assign the application role using that scope. Follow the current Microsoft instructions linked below rather than copying unreviewed tenant commands.
5. Verify authorization with `Test-ServicePrincipalAuthorization` for the dedicated mailbox and an unrelated mailbox. The former must allow sending and the latter must deny it. Allow for permission propagation. Test tenant policy and both positive/negative delivery paths before enabling production traffic.

**Do not combine a narrow RBAC scope with a broad Entra Mail.Send grant and assume the scope restricts it.** These grants are additive. Under the preferred RBAC approach, Exchange's scoped role assignment supplies application authorization; do not add an unscoped Entra Graph Mail.Send application permission. Exchange administrative authorization is required, rather than delegated user consent.

The conventional alternative is Microsoft Graph **Mail.Send (Application)** with tenant administrator consent. By itself it authorizes sending as any mailbox. An administrator must separately configure and verify a supported mailbox restriction before choosing that alternative. Do not grant broad permission merely to make a failing test pass. Ordinary Outlook delegated Send As permission is not a substitute for this app-only authorization.

## Provider configuration

Set environment variables through the deployment secret/configuration system:

| Variable | Value/source |
| --- | --- |
| `MAIL_DELIVERY` | `graph` |
| `M365_TENANT_ID` | Tenant UUID |
| `M365_CLIENT_ID` | Application/client UUID |
| `M365_CLIENT_SECRET` | Application secret value from the secret store |
| `M365_SENDER` | `AccountManagement@zoqari.com` (configurable default; normalized to lowercase) |
| `ENVIRONMENT` | `production` |
| `FRONTEND_ORIGIN` | Actual public HTTPS Signal origin, used in links |
| `COOKIE_SECURE` | `true` |
| `DATABASE_URL` | Approved production PostgreSQL configuration through secrets |

Do not copy these into committed `.env` files. Production also requires existing application/worker/storage controls described in SIGNAL-HANDOFF.md. Changing `MAIL_FROM` affects the SMTP adapter, not Graph: Graph uses `M365_SENDER` in `/users/{sender}/sendMail`.

Local development remains `MAIL_DELIVERY=local` with a private `MAIL_OUTBOX_DIR`; it needs no Entra credentials and sends no real mail. Keep the directory outside web-served paths and access restricted with OS permissions. Outbox messages contain one-use credentials: never commit, expose or share them. `disabled` fails closed. Existing TLS SMTP remains supported for compatibility; Graph is the intended Microsoft 365 provider. Local/disabled providers are forbidden in production by configuration validation.

## Runtime behavior and delivery limits

The existing account-mail abstraction selects local, SMTP or Graph. Existing verification codes/links, password resets and team invitations use the same callers; SMTP and Graph share message templates. An account-notice template is available, but the Downloads Platform Admin/account-administration workflows were not included in this focused merge. Administrators never receive reset/verification tokens from account APIs.

Graph obtains an app-only token from the fixed tenant OAuth v2 token endpoint using client credentials and `https://graph.microsoft.com/.default`. A private in-process token cache refreshes before expiry; no refresh token is stored. Calls use fixed Microsoft HTTPS hosts, a 15-second timeout and no redirects. The secret is masked in settings representations. Provider bodies, credentials and token values are not logged or returned.

Only HTTP **202 Accepted** counts as submission. It does **not** prove delivery. Inspect sent items, Exchange message trace, quarantine/bounce policies and recipient delivery during operator acceptance. A failed send is not automatically retried; 401 clears the token cache for the next explicit request. A lost response can still mean Microsoft accepted a message: avoid blind retries.

Existing account/invitation flows retain their failure handling. Email submission and database commit cannot form one transaction: partial notifications or an email whose database transaction later fails remain possible. A durable transactional outbox, idempotent dispatch strategy and operational mail health monitoring are recommended before wider production use. Generic public forgot-password responses continue to avoid account enumeration; use sanitized backend mail-failure events for diagnosis.

## Operator acceptance (not performed live)

- This Graph adapter requires no database migration. Existing Signal/Call Intelligence migrations are independent and were not changed by this merge; verify the application's intended database before normal local operation.
- Validate environment configuration without printing secrets; restart the service to pick up configuration and clear cached credentials.
- Confirm scoped authorization allows only the dedicated sender, including a negative test for another mailbox.
- In an explicitly approved test account, request verification, password reset and team invitations. Verify actual delivery from the dedicated mailbox and correct links for the configured frontend origin. Platform-admin replacement-Owner invitations and account email-change flows are outside this merge.
- Redeem a reset link once, verify previous sessions are revoked and a second redemption fails.
- Exercise permission-denied, expired-secret and network failure paths; verify sanitized logs and clear failure messages without false delivery claims.
- Rotate the application secret through the secret manager, restart and retest before removing the old credential. Never rotate mailbox passwords for this integration.

## Microsoft references

- [Exchange Online Application RBAC](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac)
- [Graph sendMail API and 202 semantics](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0)
- [Microsoft identity client credentials flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
