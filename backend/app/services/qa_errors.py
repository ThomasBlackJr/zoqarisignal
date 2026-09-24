"""Typed QA failures with deliberately small, non-sensitive diagnostic payloads."""

from enum import StrEnum

from pydantic import ValidationError


class QAReason(StrEnum):
    TRANSCRIPT_CONTEXT = "transcript_context_mismatch"
    SCHEMA_INVALID = "schema_invalid"
    CATEGORY_SET = "category_set_mismatch"
    CATEGORY_MAXIMUM = "category_maximum_mismatch"
    CATEGORY_SCORE = "category_score_out_of_range"
    EVIDENCE_EMPTY = "evidence_empty"
    EVIDENCE_NOT_VERBATIM = "evidence_not_verbatim"
    EVIDENCE_REFERENCE = "evidence_reference_invalid"
    TOTAL = "overall_total_mismatch"
    PROVIDER_OUTPUT = "provider_refused_or_incomplete"


class QAValidationError(ValueError):
    def __init__(self, reason: QAReason, *, category_index: int | None = None, evidence_index: int | None = None):
        self.reason = reason
        self.category_index = category_index
        self.evidence_index = evidence_index
        super().__init__(reason.value)

    def safe_details(self):
        details = {"validation_reason": self.reason.value}
        if self.category_index is not None:
            details["category_index"] = self.category_index
        if self.evidence_index is not None:
            details["evidence_index"] = self.evidence_index
        return details


def failure_details(exc: Exception) -> dict:
    if isinstance(exc, QAValidationError):
        return exc.safe_details()
    if isinstance(exc, ValidationError):
        # Never log str(exc), msg, input, or ctx: all can contain supplied text.
        safe_fields = {
            "categories",
            "greeting",
            "professionalism",
            "information_gathering",
            "communication",
            "resolution",
            "closing",
            "score",
            "max_score",
            "explanation",
            "evidence",
            "evidence_ids",
            "overall_score",
            "summary",
            "strengths",
            "coaching_opportunities",
            "key",
        }
        safe_codes = {
            "missing",
            "extra_forbidden",
            "int_type",
            "int_parsing",
            "greater_than_equal",
            "less_than_equal",
            "string_type",
            "string_too_short",
            "list_type",
            "model_type",
            "model_attributes_type",
            "literal_error",
        }
        issues = []
        for error in exc.errors(include_input=False, include_context=False, include_url=False)[:12]:
            issues.append(
                {
                    "path": [p if type(p) is int or p in safe_fields else "unknown_field" for p in error["loc"]],
                    "code": error["type"] if error["type"] in safe_codes else "invalid_value",
                }
            )
        return {"validation_reason": QAReason.SCHEMA_INVALID.value, "schema_issues": issues}
    return {"validation_reason": "unclassified_qa_error"}
