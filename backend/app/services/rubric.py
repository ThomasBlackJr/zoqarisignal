from ..schemas import QAResult
from .qa_errors import QAReason, QAValidationError

VERSION = "1.0"
RUBRIC = [
    {
        "key": "greeting",
        "label": "Greeting",
        "max_score": 10,
        "criteria": "Welcomes the caller and identifies the dispatcher or company.",
    },
    {
        "key": "professionalism",
        "label": "Professionalism",
        "max_score": 20,
        "criteria": "Uses respectful language, empathy, and ownership. Do not infer vocal tone from text.",
    },
    {
        "key": "information_gathering",
        "label": "Information Gathering",
        "max_score": 20,
        "criteria": "Confirms relevant delivery details, caller needs, and identifiers.",
    },
    {
        "key": "communication",
        "label": "Communication",
        "max_score": 20,
        "criteria": "Provides clear, understandable information and confirms understanding.",
    },
    {
        "key": "resolution",
        "label": "Resolution",
        "max_score": 20,
        "criteria": "Offers a concrete next step, realistic expectation, and ownership of follow-up.",
    },
    {
        "key": "closing",
        "label": "Closing",
        "max_score": 10,
        "criteria": "Summarizes next steps, offers further help, and closes courteously.",
    },
]


def validate_result(value, transcript: str, rubric=None) -> QAResult:
    result = QAResult.model_validate(value.model_dump() if isinstance(value, QAResult) else value)
    expected = {item["key"]: item["max_score"] for item in (RUBRIC if rubric is None else rubric)}
    if len(result.categories) != len(expected) or {c.key for c in result.categories} != set(expected):
        raise QAValidationError(QAReason.CATEGORY_SET)
    for index, category in enumerate(result.categories):
        if category.max_score != expected[category.key]:
            raise QAValidationError(QAReason.CATEGORY_MAXIMUM, category_index=index)
        if category.score > category.max_score:
            raise QAValidationError(QAReason.CATEGORY_SCORE, category_index=index)
        for evidence_index, quote in enumerate(category.evidence):
            if not quote.strip():
                raise QAValidationError(QAReason.EVIDENCE_EMPTY, category_index=index, evidence_index=evidence_index)
            if quote not in transcript:
                raise QAValidationError(
                    QAReason.EVIDENCE_NOT_VERBATIM, category_index=index, evidence_index=evidence_index
                )
    if sum(c.score for c in result.categories) != result.overall_score:
        raise QAValidationError(QAReason.TOTAL)
    return result


LEGACY_ID = "00000000-0000-0000-0000-000000000001"


def rubric_items(rubric):
    return [
        {"key": c.key, "label": c.name, "description": c.description, "max_score": c.weight, "criteria": c.criteria}
        for c in rubric.categories
    ]


def active_rubric(db, organization_id):
    from sqlalchemy import select
    from ..models import Rubric

    value = db.scalar(
        select(Rubric)
        .where(Rubric.status == "ACTIVE", Rubric.organization_id == organization_id)
        .order_by(Rubric.activated_at.desc(), Rubric.id)
        .limit(1)
    )
    if value is None:
        raise ValueError("active_rubric_missing")
    items = rubric_items(value)
    if not items or sum(c["max_score"] for c in items) != 100:
        raise ValueError("active_rubric_invalid")
    return value


def seed_legacy(db):
    """Used by isolated create_all tests; production seeding belongs to Alembic."""
    from ..models import Rubric, RubricCategory

    rubric = Rubric(
        id=LEGACY_ID,
        name="Dispatch QA",
        version=VERSION,
        status="ACTIVE",
        activated_at=0,
        organization_id="00000000-0000-0000-0000-000000000002",
    )
    rubric.categories = [
        RubricCategory(
            key=c["key"],
            name=c["label"],
            description="",
            weight=c["max_score"],
            criteria=c["criteria"],
            display_order=i,
        )
        for i, c in enumerate(RUBRIC)
    ]
    db.add(rubric)
    db.flush()
    return rubric


def create_starter_rubric(db, organization_id, created_by):
    """A tenant-owned starter version; customers can duplicate and customize it."""
    import time
    from ..models import Rubric, RubricCategory

    rubric = Rubric(
        name="Dispatch QA starter",
        version=VERSION,
        status="ACTIVE",
        organization_id=organization_id,
        created_by=created_by,
        activated_at=time.time(),
    )
    rubric.categories = [
        RubricCategory(
            key=c["key"],
            name=c["label"],
            description="",
            weight=c["max_score"],
            criteria=c["criteria"],
            display_order=i,
        )
        for i, c in enumerate(RUBRIC)
    ]
    db.add(rubric)
    db.flush()
    return rubric


def selected_rubric(db, organization_id, rubric_id=None):
    from fastapi import HTTPException
    from sqlalchemy import select
    from ..models import Rubric

    if rubric_id is None:
        try:
            return active_rubric(db, organization_id)
        except ValueError as exc:
            raise HTTPException(409, "Publish a scorecard before uploading.") from exc
    value = db.scalar(select(Rubric).where(Rubric.id == rubric_id, Rubric.organization_id == organization_id))
    if value is None:
        raise HTTPException(404, "Scorecard not found")
    if value.status != "ACTIVE":
        raise HTTPException(409, "Select a currently published scorecard.")
    return value
