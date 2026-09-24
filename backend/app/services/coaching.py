"""AI selects a bounded intervention; Signal alone authors factual claims and requirements."""

from typing import Literal
from ..schemas import StrictModel


class CoachingChoice(StrictModel):
    action: Literal["review_examples", "team_practice", "scorecard_walkthrough"]
    tone: Literal["warm", "concise"]


ACTIONS = {
    "review_examples": "Consider reviewing the linked interactions with the team and comparing the evidence with the scorecard requirements.",
    "team_practice": "Consider a short team practice session using the scorecard requirements, followed by a review of future evaluated interactions.",
    "scorecard_walkthrough": "Consider walking through the scorecard requirements at the next team meeting and inviting questions about how to apply them.",
}


def grounding(issue):
    # No names, user IDs, call IDs, quotes, explanations or inferred reasons leave Signal.
    return dict(
        scope="Organization; all time; current employee assignments",
        finding="Category below maximum points; not a criterion-level policy failure",
        category=issue["name"],
        scorecard_version=issue["rubric_version"],
        requirement=issue["criteria"],
        description=issue["description"],
        occurrences=issue["occurrences"],
        eligible_interactions=issue["eligible"],
        affected_employees=issue["affected_employees"],
        unassigned_interactions=issue["unassigned"],
        aggregate_evidence={
            "category_maximum": issue["max_score"],
            "below_maximum_scores": sorted({e["category_score"] for e in issue["evidence"]}),
            "audited_overrides": sum(e["overridden"] for e in issue["evidence"]),
            "synthetic_interactions": sum(e["is_demo"] for e in issue["evidence"]),
        },
        permitted_actions=ACTIONS,
    )


def materialize(issue, choice, provider, created_at):
    choice = CoachingChoice.model_validate(choice)
    observation = (
        f"{issue['occurrences']} of {issue['eligible']} current evaluated interactions "
        f"({issue['percent']}%) scored below maximum in {issue['name']}; "
        f"{issue['affected_employees']} assigned employees affected, "
        f"{issue['unassigned']} unassigned interactions. "
        "All time, current assignments. This is a category score observation, not a policy-failure count."
    )
    synthetic_count = sum(e["is_demo"] for e in issue["evidence"])
    if synthetic_count:
        observation += f" Includes {synthetic_count} synthetic demonstration occurrences."
    action = ACTIONS[choice.action]
    opening = (
        "Thank you for your work supporting our customers."
        if choice.tone == "warm"
        else "A quality review reminder for the team."
    )
    body = (
        f"Team,\n\n{opening}\n\n{observation}\n\n"
        f"Scorecard: {issue['rubric_name']}, version {issue['rubric_version']}.\n"
        f"Exact category requirements:\n{issue['criteria']}\n\n{action}\n\n"
        "Please bring questions or examples to our next discussion. Thank you."
    )
    return dict(
        observation=observation,
        recommendation=action,
        subject=f"Review reminder: {issue['name']}",
        body=body,
        provider=provider,
        created_at=created_at,
        synthetic=provider == "demo",
        fingerprint=issue["fingerprint"],
    )
