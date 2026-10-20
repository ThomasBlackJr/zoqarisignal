# Resend transactional mail

Resend is an additional provider. Local outbox, SMTP and Microsoft Graph remain supported. No database migration, DNS change or Microsoft 365 change is required by this code.

In backend/.env, preserve existing settings and add/update these values locally:

```dotenv
MAIL_DELIVERY=resend
RESEND_API_KEY=
RESEND_FROM=AccountManagement@zoqari.com
```

Enter your real API key in that private file yourself. Never paste it into chat, commit it, or pass it as a command-line argument. A blank key deliberately fails configuration validation when Resend is selected. The existing .gitignore excludes .env. Existing .env files are preserved by this implementation; .env.example contains no credentials.

The sender is formatted as `Zoqari Signal <AccountManagement@zoqari.com>`. RESEND_FROM accepts a bare validated mailbox; Signal adds the display name. The zoqari.com sending domain was reported verified by the operator. This implementation does not alter or independently certify domain/DNS configuration.

The adapter uses the shared Signal templates for verification, password resets, invitations, account notices and flagged-call alerts. Both plain text and HTML, including existing links/codes and HTML escaping, are sent through the fixed https://api.resend.com/emails endpoint. It uses the existing httpx dependency, a 15-second timeout, no redirects and no automatic retries. HTTP 200 with a nonempty submission ID counts as accepted, not delivered. Failures and uncertain responses become MailUnavailable without exposing provider bodies, API keys or message contents. Check the provider dashboard before explicitly retrying an uncertain submission.

Official API contract: [Resend Send Email](https://resend.com/docs/api-reference/emails/send-email).

Keep your normal development database/provider settings for local verification. Production additionally requires the existing HTTPS, secure-cookie and persistent PostgreSQL safeguards. Switching providers does not grant account access or entitlements. Graph settings and its transport remain intact and can still be selected with MAIL_DELIVERY=graph.

## First controlled test

From the backend directory, after entering the key, validate without sending:

```powershell
..\.venv\Scripts\python.exe -m tools.send_test_email
```

When you explicitly choose to send one real test message, replace the recipient with an address you control:

```powershell
..\.venv\Scripts\python.exe -m tools.send_test_email --to "YOUR_TEST_EMAIL_ADDRESS" --send
```

The helper reads Settings from the local environment/.env, requires Resend mode, performs one submission only and prints no credentials or raw provider response. It does not import the application, start a worker, access a database or send real account tokens. Without --send it sends nothing. No real external test email is sent during implementation. Verify actual delivery in the inbox and Resend dashboard; a successful submission is not delivery confirmation.

## Implementation validation — 2026-10-18

31 Resend unit cases and all 12 existing Graph cases passed. The full backend suite passed 336 tests with one optional PostgreSQL integration skip. All 17 isolated browser workflows passed; the runner was interrupted only after all successful outcomes were recorded because Windows test-server teardown lingered. Ruff, frontend ESLint, TypeScript and the production build passed. Settings loaded the requested mode/sender from a temporary .env with a synthetic key, without HTTP. Existing private .env, Graph transport, Call Intelligence implementation, dependency lock and migrations were preserved. All Resend/Graph unit submissions were mocked; browser account flows used a private local outbox. Live API authentication/delivery remains for the operator's explicit test.
