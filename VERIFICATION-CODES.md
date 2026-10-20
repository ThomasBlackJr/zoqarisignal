# Six-digit email verification

Registration and resend use the existing verification service and `verify_code` email template. The current checkout already had the secure code infrastructure; this update removes legacy verification-link redemption and makes the code prominent in the shared HTML template. Password-reset links are unchanged.

1. Register with your business email and password.
2. Signal requests a code through the selected mail provider and opens the code screen. With `MAIL_DELIVERY=resend`, Resend sends from `Zoqari Signal <AccountManagement@zoqari.com>`.
3. The subject is **Your Zoqari Signal verification code**. Enter the six-digit code within 15 minutes and select Verify email.
4. Successful verification immediately removes the code and establishes the verified session. Continue to Account to create/join the normal organization workflow.
5. Resend code becomes available after 60 seconds. Requesting a replacement rotates the private challenge and invalidates the previous one. Use the newest message.

Code generation uses `secrets.randbelow(1000000)` with zero padding. Only a salted Argon2 code hash and a hash of the opaque challenge are persisted. Plaintext codes are delivered to the recipient, never returned by account APIs or logged. Explicit local development mode writes a private outbox instead of sending mail; tests use synthetic accounts and this private outbox or mocked Resend HTTP.

Five failed guesses exhaust a challenge. Account endpoints have the existing 20-request/hour/IP limit; code issuance has a persisted 60-second/account cooldown. Registration responses remain generic for existing/new addresses, and invalid/expired/used codes have one generic error. The IP limiter is process-local; shared/edge abuse controls are still required before a multi-instance public deployment. The signed-in user or an opaque challenge is required to redeem a code; codes are not global email credentials.

Public registration remains generic even on provider submission failure; failed issuance rolls back the new account and code, and a sanitized operator event records the failure. A requested-code response is not a delivery confirmation. Check provider health if a message never arrives.

Legacy verification-token submissions are rejected. Existing unverified users with an old link should sign in and request a code. Verification-only link issuance is disabled; password recovery still uses its existing expiring single-use links and session revocation. The legacy `verify` template is retained for provider compatibility, but the account verification endpoint accepts codes only.

No migration or model change is required: the existing `verification_codes` table was introduced by migration `m391792bce12`. Existing migrations are untouched. Resend and Graph transports, private .env, Call Intelligence and its migrations are unchanged.

## Validation

Full backend: 345 passed, one optional test skipped. Graph and Resend regression tests passed. Ruff, frontend lint and TypeScript passed. Browser suite: 16 passed, including registration, incorrect code, resend cooldown, replacement, successful verification, password recovery and Call Intelligence; the manager-team test failed (an account connection reset on one run, a team-page 404 on the rerun). The Windows browser runner required interruption after recording all outcomes because server teardown stalled.

The manager-team test also reproduced its team-page 404 when run alone. Its implementation was not changed by this task.

Production builds compiled and type-checked, but static generation failed with Windows `EPERM` while creating generated `.segments` directories. Both Turbopack and webpack were attempted; an isolated source copy reproduced the filesystem failure. A successful production build is still unconfirmed. No real email was sent.

## First explicitly approved live flow test

Retain the normal local configuration and set `MAIL_DELIVERY=resend`, `RESEND_FROM=AccountManagement@zoqari.com`, and your API key privately in backend/.env. Never paste or print the key. See RESEND-SETUP.md. With the local backend/frontend running, open registration:

```powershell
Start-Process 'http://localhost:3000/register'
```

Register a new test address you control, check the actual inbox, enter the received code, and select Verify email. This sends a real verification email only when you submit the registration/resend form; the implementation/testing step sends no real email. The generic `tools.send_test_email` helper tests mail transport only and does not exercise registration/code redemption.
