"""Ground model evidence in source IDs; derive redundant rubric values in code.

The provider wire format is internal. Every provider still returns QAResult and
the processing pipeline independently validates it before storing anything.
"""

import re
from typing import Annotated

from pydantic import Field, create_model

from ..schemas import QAResult, StrictModel
from .qa_errors import QAReason, QAValidationError
from .rubric import RUBRIC, validate_result


def evidence_sources(text: str) -> list[str]:
    # Exact contiguous source spans, not summaries, normalized text, or model quotes.
    # Newlines and sentence endings give useful selection boundaries. Very long
    # sentences are split into bounded spans without altering their characters.
    sources = []
    for match in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|\n|$)", text, re.DOTALL):
        span = match.group().rstrip()
        for start in range(0, len(span), 600):
            excerpt = span[start : start + 600].strip()
            if excerpt:
                sources.append(excerpt)
    return sources


def response_format(source_count: int, rubric=None) -> type[StrictModel]:
    if source_count < 1:
        raise QAValidationError(QAReason.EVIDENCE_EMPTY)
    reference = Annotated[int, Field(ge=0, le=source_count - 1, strict=True)]
    category_fields = {}
    for item in RUBRIC if rubric is None else rubric:
        category = create_model(
            f"QA_{item['key']}",
            __base__=StrictModel,
            score=(Annotated[int, Field(ge=0, le=item["max_score"], strict=True)], ...),
            explanation=(Annotated[str, Field(min_length=1)], ...),
            evidence_ids=(list[reference], ...),
        )
        category_fields[item["key"]] = (category, ...)
    categories = create_model("QARubricCategories", __base__=StrictModel, **category_fields)
    # The model must not supply an overall score or rubric maxima. They are
    # deterministic, not judgment calls, and extra fields are forbidden.
    return create_model(
        "QAAssessment",
        __base__=StrictModel,
        categories=(categories, ...),
        summary=(Annotated[str, Field(min_length=1)], ...),
        strengths=(list[str], ...),
        coaching_opportunities=(list[str], ...),
    )


def materialize(assessment, sources: list[str], transcript: str, schema: type[StrictModel], rubric=None) -> QAResult:
    # Revalidate SDK-parsed instances as data too: model_construct or mutation
    # must not bypass score bounds, unknown fields, or reference restrictions.
    data = assessment.model_dump() if isinstance(assessment, StrictModel) else assessment
    parsed = schema.model_validate(data).model_dump()
    categories = []
    for category_index, item in enumerate(RUBRIC if rubric is None else rubric):
        category = parsed["categories"][item["key"]]
        evidence = []
        for evidence_index, source_id in enumerate(category["evidence_ids"]):
            # Defense in depth independent of the generated schema's bounds.
            if type(source_id) is not int or not 0 <= source_id < len(sources):
                raise QAValidationError(
                    QAReason.EVIDENCE_REFERENCE, category_index=category_index, evidence_index=evidence_index
                )
            evidence.append(sources[source_id])
        categories.append(
            {
                "key": item["key"],
                "score": category["score"],
                "max_score": item["max_score"],
                "explanation": category["explanation"],
                "evidence": evidence,
            }
        )
    result = {
        "overall_score": sum(category["score"] for category in categories),
        "categories": categories,
        "summary": parsed["summary"],
        "strengths": parsed["strengths"],
        "coaching_opportunities": parsed["coaching_opportunities"],
    }
    return validate_result(result, transcript, rubric)
