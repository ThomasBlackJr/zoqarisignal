# Transcript speaker-turn update

## What identifies a speaker today

The existing OpenAI adapter is unchanged: whisper-1 returns timestamped text segments but no reliable speaker separation. The two saved local transcripts each had 25 segments and zero speaker IDs. True speaker diarization is a distinct provider capability; see the [official transcription documentation](https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization).

`LocalSpeakerRoles` is a separate offline post-transcription inference service. It recognizes narrow dispatch/caller language cues, leaves short/ambiguous text UNKNOWN, and refuses to infer a role from first/second speaker order. Supplied speaker IDs support contextual role hints only when cues for that ID are consistent. Conflicting cues produce UNKNOWN. CALLER is the other party, not a customer subtype. Role hints are visibly marked **Inferred**, confidence is null because it is not calibrated, and no acoustic speaker identity is fabricated.

This is deliberately conservative. Both saved Whisper transcripts remain at 25 displayed units: two tentative dispatcher labels and 23 UNKNOWN units. They benefit from range labels, explicit uncertainty, exact source text, and the raw-view toggle, but cannot honestly be collapsed into fewer speaker turns without stronger speaker information. Inferred labels may be wrong (including outbound calls or reported speech); the audio remains authoritative. Future true diarization can supply IDs, and a separate role adapter can supply verified ID-to-role mappings.

## Grouping and original data

`ConversationService` merges adjacent segments only when known speaker IDs match, or when both have the same non-UNKNOWN inferred role in the two-party-call model. It never merges differing IDs even if both have the same role. UNKNOWN without an ID is not a shared speaker; it breaks grouping. A supplied shared ID can support grouping even if its role remains UNKNOWN. Overlapping/backward timestamp boundaries are kept separate.

Turns retain the first start and actual final end. Missing starts/ends stay missing; the final segment's start is never substituted for its end. Each turn stores original source offsets, source segment indices, optional speaker ID, role, role provenance, and optional confidence. Its text is an exact contiguous slice of canonical `Transcript.text`; concatenating all turns reproduces that text, including whitespace. No paraphrasing, normalization, or summarization is used. If the raw segments cannot be aligned without losing canonical text, the complete original text is shown as UNKNOWN, without invented timestamps.

The raw `Segment`/`Transcription` schemas, transcription provider adapter, and QA provider/numbered-excerpt validation are unchanged. Formatting is a separate step with a safe fallback; even a formatting/cache exception cannot invalidate the committed transcription or block otherwise successful QA. QA retries still reuse saved transcripts.

## Database and existing calls

Alembic revision `b192cb82ae01` adds only nullable JSON `transcripts.conversation`. New calls cache the derived presentation separately using a format version and raw-source fingerprint. Existing calls with null or stale data derive locally on read; GET does not write the cache or invoke either provider. No backfill or paid reprocessing is required.

The migration was applied through Alembic, not manual SQL schema edits. Before/after checks showed the two existing raw transcripts and existing QA result were unchanged. Restart DRIVE's backend to load the new code. `Start-Drive.ps1` also runs the migration on other installations.

## Files changed

Backend:
- `app/conversation_schemas.py` (new): derived role/turn/conversation contracts.
- `app/services/speaker_roles.py` (new): replaceable role-service protocol and conservative offline implementation.
- `app/services/conversations.py` (new): exact alignment, grouping, cache selection, and safe fallback.
- `app/models.py`: nullable derived cache field.
- `app/services/processing.py`: isolated derived-cache step; original QA input unchanged.
- `app/main.py`: additive `transcript.conversation` response alongside unchanged raw fields.
- `migrations/versions/b192cb82ae01_add_transcript_conversation.py` (new).
- `tests/test_conversations.py` (new): 29 tests/cases.

Frontend:
- `components/transcript-viewer.tsx` (new): conversation/raw views, role distinction, inference disclosure, range seeking.
- `app/(workspace)/calls/[id]/page.tsx`: uses the extracted viewer; unrelated UI unchanged.
- `lib/api.ts`: additive conversation types.
- `app/globals.css`: transcript-only styling.
- `tests/workflow.spec.ts`: extended workflow checks and new grouped-view browser test.
- `next.config.ts`, `playwright.config.ts`, `eslint.config.mjs`, `tsconfig.json`: isolate generated browser-test output from a running local dev server.

Documentation/package support: `.gitignore`, `README.md`, `VALIDATION.md`, `TRANSCRIPT-PLAN.md`, this report, and the refreshed source ZIP. The workspace packaging script excludes the separate test build directory.

## Verification

- **80 backend tests passed**, including all prior QA regression and retry tests.
- Backend Ruff and Alembic model-drift check passed.
- **2 Playwright tests passed**, covering the full upload-to-QA workflow and grouped speaker labels, ranges, audio seeking, raw segments, exact text, and mobile width.
- Desktop/mobile transcript screenshots were inspected; UI fixtures are synthetic and do not claim to be diarization results from real audio.
- Frontend ESLint, TypeScript, and production build all passed. Generated `.next-e2e` output is excluded from source linting.
- No live transcription/QA calls, automatic retries, or reprocessing were performed. Existing live provider code and exact-evidence contracts remain intact; compatibility was verified with the full regression suite and unchanged stored data.
