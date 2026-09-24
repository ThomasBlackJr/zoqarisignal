# Day 2 Part 2 implementation plan

Audit: Part 1 handoff read completely; no Git repository; Part 1 source archive retained. Existing Call records, queue, strict QA, tenant/entitlement gate and immutable review history are authoritative. Corporate reference stays read-only.

1. Persist batch manifests and per-file outcomes; bounded individual transfers create normal Call records. Exact byte hashing prevents duplicate processing within the organization. An interrupted transfer can be replaced; accepted uploads continue through the server queue without a browser.
2. Separate tracked Employee records from authenticated User accounts; tenant-safe employee management, audited assignment, current-performance summaries.
3. Capture corrected speaker context and revision for each new QA attempt, preserve raw transcript/evidence and previous results, flag stale results and exclude them from current aggregates until explicitly re-evaluated.
4. Scoped expiring team invitations through the existing mail adapter, no client-selected membership or Owner escalation.
5. Server-persisted constrained dashboard modules and Light/Dark/System preferences, accessible branded UI.

Implement and verify coherent systems in that order. Do not expose placeholder screens for unfinished features. Rehearse migrations on a private copy; keep live data unchanged until restart. Run regression, tenant/permission, processing, browser and build checks; update the handoff with exact delivery boundaries.

All five implementation systems are delivered. Exact limits, migration rehearsal, validation and remaining production work are in the current SIGNAL-HANDOFF.md and SIGNAL-QA.md.
