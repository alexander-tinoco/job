"""The rubric is the highest-risk part of the product (plan §4.2).

These rules are what stop a small business from shipping a rubric that produces
a screen nobody trusts.
"""

import pytest
from pydantic import ValidationError

from app.schemas.openings import CriterionIn, OpeningCreate
from app.services.rubric_templates import TEMPLATES


def _criteria(*weights: int, mandatory_first: bool = True) -> list[CriterionIn]:
    return [
        CriterionIn(name=f"Criterion {i}", weight=w, mandatory=(i == 0 and mandatory_first))
        for i, w in enumerate(weights)
    ]


def _build(**overrides: object) -> OpeningCreate:
    payload: dict[str, object] = {"title": "Backend Engineer", "criteria": _criteria(60, 40)}
    payload.update(overrides)
    return OpeningCreate(**payload)  # type: ignore[arg-type]


def test_a_valid_rubric_is_accepted() -> None:
    opening = _build()

    assert sum(c.weight for c in opening.criteria) == 100
    assert opening.warnings == []


@pytest.mark.parametrize(
    ("weights", "expected"),
    [((60, 30), "they sum to 90 (10 under)"), ((70, 45), "they sum to 115 (15 over)")],
)
def test_weights_must_sum_to_100_and_the_error_states_the_drift(
    weights: tuple[int, ...], expected: str
) -> None:
    with pytest.raises(ValidationError) as exc:
        _build(criteria=_criteria(*weights))

    assert expected in str(exc.value)


def test_a_single_criterion_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _build(criteria=_criteria(100))

    assert "at least 2 criteria" in str(exc.value)


def test_more_than_eight_criteria_are_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _build(criteria=_criteria(*([11] * 8), 12))

    assert "at most 8 criteria" in str(exc.value)


def test_duplicate_criterion_names_are_rejected() -> None:
    criteria = [
        CriterionIn(name="Python", weight=50, mandatory=True),
        CriterionIn(name="python", weight=50),
    ]

    with pytest.raises(ValidationError) as exc:
        _build(criteria=criteria)

    assert "repeated: python" in str(exc.value)


def test_a_rubric_without_a_mandatory_criterion_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _build(criteria=_criteria(60, 40, mandatory_first=False))

    assert "must be mandatory" in str(exc.value)


def test_a_dominant_criterion_warns_but_does_not_block() -> None:
    opening = _build(criteria=_criteria(70, 30))

    assert len(opening.warnings) == 1
    assert "70%" in opening.warnings[0]


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.key)
def test_every_shipped_template_passes_our_own_validation(template: object) -> None:
    """A template that fails validation would be worse than no template at all."""
    _build(criteria=template.criteria)  # type: ignore[attr-defined]
