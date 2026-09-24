# Day 2 — customer entry milestone

Baseline: 96 backend tests pass. Existing Next/FastAPI services, strict QA, immutable history and tenant filters remain authoritative.

This coherent milestone implements registration, expiring single-use email verification/password reset, verified organization creation with Owner permissions, server and worker entitlement enforcement, explicitly enabled local development entitlement activation, and persisted onboarding into the existing scorecard/upload/review journey.

No real checkout is claimed. New and migrated organizations start inactive; existing accounts remain usable for sign-in and subscription setup, with recordings/history retained. Local development activation requires explicit configuration and expires after seven days. Production cannot enable development mail or entitlements.

Email delivery is an adapter: disabled, private local development outbox, or TLS SMTP. Tokens are hashed in the database, never logged or returned by public APIs. Reset revokes sessions. Local outbox files are credentials and must stay private.

Implementation order: migration/models → account/security services and APIs → account journey and onboarding UI → regression and browser tests → migration rehearsal on a private copy → handoff. Existing operational tests explicitly seed verified, entitled organizations, rather than bypassing gates.

Deferred Day 2 continuation: employee profiles/assignment, bulk ingestion, employee/team trends and coaching analytics. Do not add placeholder navigation or claim these work. Existing single-upload and latest-evaluation dashboard remain usable after setup.
