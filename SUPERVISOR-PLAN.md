# Supervisor controls implementation plan

1. Preserve the existing source archive as a checkpoint (this workspace has no Git repository). Inspect existing services, contracts, migrations, authorization, views, and tests.
2. Add normalized rubric/category tables, immutable evaluation history, and append-only speaker/score audit records. Seed the exact original rubric through Alembic and associate existing evaluations without altering their results.
3. Capture the active rubric for each QA attempt. Parameterize the provider contract and both validation layers; retain exact numbered evidence and server totals. Explicit re-evaluation appends history and reuses saved transcription.
4. Expose server-authorized draft rubric management, publication, speaker correction, score adjustment/reset, and review completion. Reject stale edits and preserve original inference and AI results.
5. Refine the existing shell, dashboard, operational table, transcript, QA review controls, and rubric editor with accessible responsive forms and consistent visual hierarchy.
6. Test migrations and all new controls, run the complete regression suite and frontend checks/build, and exercise isolated browser workflows. No live provider requests or retranscription of saved recordings.
