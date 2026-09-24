# Working on Zoqari Signal

- Read README.md and PLAN.md, then inspect existing code before implementing changes. Prefer modifying the existing service or component over creating parallel implementations.
- Preserve the Next.js / FastAPI separation and modular architecture. Routes orchestrate; service adapters integrate providers; Pydantic defines validated contracts.
- Never hard-code AI providers in route handlers or UI. Extend the registries in `backend/app/services/providers.py` and honor the service protocols. Keep credentials in environment variables.
- Keep rubric loading and validation centralized in `backend/app/services/rubric.py`; published normalized database rubrics are immutable. Do not scatter grading rules through unrelated components. Validate all structured AI output before persistence, including evidence and score arithmetic.
- Never commit secrets, session tokens, real recordings, transcripts, databases, or `.env` files. Demo mode must remain visibly synthetic. Do not log provider exception messages or request payloads.
- Add an Alembic migration for every schema change. Never replace migrations with startup `create_all`. Production uses one backend process until a distributed worker design is intentionally introduced.
- Keep authentication server-enforced, cookies HttpOnly, and audio access authenticated. Preserve the central permission matrix: OWNER/ADMIN manage tenant users/scorecards; MANAGER/REVIEWER/legacy SUPERVISOR review; EMPLOYEE has basic account access only.
- Preserve committed transcription when QA fails. Avoid automatic retries that can generate unexpected provider charges.
- Update meaningful tests for important behavior. Run backend pytest and Ruff; frontend ESLint, TypeScript, and production build. Run Playwright for workflow/UI changes.
- Do not implement the future-feature list without an explicit request. Keep the MVP simple and extend the existing models/services when needed.
- Test data belongs in temporary databases. Browser tests launch isolated servers on 3001/8001; never point their bootstrap at a real database.

- Read SIGNAL-PLAN.md, SIGNAL-HANDOFF.md and SIGNAL-QA.md before continuing commercialization. Do not restart completed controls or branding work.
- The corporate Zoqari project is read-only reference. Never change it from this application task.
- Require organization ownership on every new resource. Filter through the authenticated organization before reading or mutating IDs, including media/history/audits. Add two-tenant tests for every new resource.
- Keep original AI evaluation records and source transcripts immutable. Manual changes append audit records; new evaluations append history.
- Do not claim public onboarding, billing, integrations or production readiness before those milestones actually exist and pass validation.
- Read DAY2-PLAN.md and the current Day 2 section of SIGNAL-HANDOFF.md. Preserve verified account/membership/entitlement checks in all operational APIs and workers. No free operational access on signup or organization creation; development grants/local mail are explicitly enabled, loopback-only and forbidden in production.
- Account tokens and local mail files are credentials. Never log or publish them. Preserve one-use atomic redemption and reset session revocation. Keep the existing provider abstraction and stored-transcript retry behavior.

- Day 2 Part 2: read DAY2-PART2-PLAN.md and the current handoff first. Preserve batch manifest/item idempotency and per-tenant duplicate linking, Employee/User separation, append-only assignment history, pinned corrected-transcript evaluation context, and exclusion of outdated/historical results from current performance. Team acceptance must never overwrite an existing account password, replace existing organization membership, or grant Owner. Dashboard and appearance preferences belong to the authenticated user only.

- Hierarchy: preserve Employee/User separation and explicit manager eligibility, same-organization unique explicit login links, cycle protection under the organization mutation lock, append-only reporting/link audit, and interaction-weighted current direct-report analytics. Employee/User linking does not change authorization. Do not silently enable own-team access or historical attribution.

- Product controls: multiple published scorecards are intentional; never auto-archive another version on publish. Pin explicit scorecard selection before processing and preserve the previous-version exception only for corrected reevaluation. Permanent delete is Owner/Admin-only, tenant-scoped, with dependency checks and content-free audit. Preserve durable audio-cleanup jobs and batch tombstones.
