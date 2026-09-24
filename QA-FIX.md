# Live QA validation investigation and fix

## Observed cause and limits of the evidence

Call `4aaceed8-330b-4c46-ac9f-bd42f630645e` has a successfully committed transcript and no QA evaluation. Its original QA response was not retained (`store=False`, and failed evaluations are not stored). The old log contained only the exception class, so its exact historical validation branch cannot be recovered.

Two QA-only diagnostic requests were made against the saved transcript using the original implementation. The first passed. The second reproduced a `ValueError`: **evidence was not a verbatim transcript excerpt**. Both responses parsed successfully into the structured-output schema. In the failing replay:

- All six category keys and rubric maxima were correct, and all category scores were within bounds.
- Two evidence quotations failed exact matching; one differed only in capitalization.
- The model also supplied an overall score of 90 while its category scores summed to 100.
- Evidence validation ran before total validation, so it raised first and masked the second defect.

This is a reproduced failure on the same saved transcript, not a claim that the discarded original response has been retrieved. HTTP 200 and schema-valid JSON do not establish that evidence and cross-field arithmetic satisfy DRIVE's domain constraints.

## Root fix

The old provider contract asked the model to recopy quotations exactly and independently calculate a redundant total. It described the rubric in the prompt but the generic schema did not structurally enforce each category's identity or specific maximum.

The new internal wire schema is generated from the existing rubric. It requires exactly the rubric's category keys and constrains each category score to that category's bounds. It asks the model to select numbered, exact source excerpts rather than rewrite quotes. DRIVE resolves those references against its own transcript excerpts, supplies the authoritative rubric maxima, and computes the total from the validated category scores. Unknown references, extra fields (including model-provided totals), missing categories, wrong types, and invalid scores fail validation.

The externally visible `QAResult` and provider `evaluate(text) -> QAResult` interface are unchanged. The original case-sensitive exact-evidence check and category/total checks still run before persistence. No lowercasing, fuzzy matching, paraphrase matching, score clamping, exception suppression, or automatic billable retries were added. Pydantic instances are revalidated as data so mutation cannot bypass constraints. Transcription code and the database schema were not changed.

## Files changed

- `backend/app/services/providers.py`: OpenAI QA uses the grounded wire schema and materializes the existing result format. Transcription methods are unchanged.
- `backend/app/services/qa_contract.py` (new): exact transcript source spans, rubric-derived response schema, source-reference resolution, deterministic maxima/total, final validation.
- `backend/app/services/qa_errors.py` (new): typed validation reasons and strictly sanitized diagnostic fields.
- `backend/app/services/rubric.py`: existing safeguards preserved with specific typed failure reasons; revalidates model instances.
- `backend/app/services/processing.py`: logs specific safe QA diagnostics and stores a useful failure message while retaining the transcript.
- `backend/tests/test_qa_regression.py` (new): synthetic reproduction of observed evidence/total mismatch; grounded contract, invalid references/scores, source integrity, real SDK parsing over mocked HTTP 200, privacy-safe diagnostics, and retry with no transcription call.
- `backend/tests/test_providers.py`: refusal/prompt assertions updated for the internal provider contract.
- `README.md`, `VALIDATION.md`, and this report: configuration-independent behavior, diagnostic codes, and validation evidence documented.

No changes were needed to the frontend, public API response shape, rubric weights/version, environment settings, database, or stored call data. The source ZIP was refreshed from the updated source without credentials or customer data.

## Verification

- 51 backend tests passed; Ruff passed.
- Frontend ESLint, TypeScript, and production build passed.
- The fixed adapter was exercised against live OpenAI using the existing saved transcript. All six categories passed; total and category sum were both 100; every evidence excerpt matched exactly. This was a diagnostic validation, not a persisted evaluation, and a future evaluation can produce a different judgment score.
- No transcription request was made during the investigation. The existing transcript was checked unchanged after the live verification, and the existing failed call was left ready for the user's Retry.
- The regression fixture is synthetic and reproduces the observed failure structure; it contains no private transcript or live response text.

## Using the fix

Restart DRIVE's backend (or stop the launcher with Ctrl+C and run `Start-Drive.ps1` again) because its current process holds the old code. Then open the existing failed call and choose **Retry processing**. No new upload is needed. A stored transcript causes the processing pipeline to skip transcription and issue only the QA request; that may incur QA usage charges but not another transcription charge. The retry regression test explicitly asserts zero transcriber invocations and unchanged transcript content and creation timestamp.
