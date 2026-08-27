"""Layers 3 and 4 of the anti-injection design: quote checking and scoring."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai.schema import EvaluationOutput
from app.ai.verify import VerifiedCriterion, find_quote, normalise, verify, weighted_score

FIXTURES = Path(__file__).parent / "fixtures"
RESUME = "Ada Lovelace\nSix years of Python\nand PostgreSQL at scale."
WEIGHTS = {"Python": 60, "Postgres": 40}


def _output(**overrides: object) -> EvaluationOutput:
    payload: dict[str, object] = {
        "criteria": [
            {
                "criterion_name": "Python",
                "score": 4,
                "justification": "Six years.",
                "evidence": ["Six years of Python"],
            },
            {
                "criterion_name": "Postgres",
                "score": 3,
                "justification": "At scale.",
                "evidence": ["PostgreSQL at scale"],
            },
        ],
        "relevant_years_experience": 6.0,
        "mandatory_requirements_met": True,
        "missing_requirements": [],
        "risks": [],
        "detected_skills": ["Python"],
        "summary": "Solid.",
    }
    payload.update(overrides)
    return EvaluationOutput.model_validate(payload)


# --- Quote verification (layer 4) ---


def test_a_quote_spanning_a_line_break_is_found() -> None:
    """Extraction rebuilds line breaks, so raw comparison would fail real quotes."""
    result = find_quote("Six years of Python and PostgreSQL", RESUME)

    assert result.found is True
    assert RESUME[result.start : result.end].replace("\n", " ") == (
        "Six years of Python and PostgreSQL"
    )


def test_offsets_point_into_the_original_text_not_the_normalised_one() -> None:
    result = find_quote("PostgreSQL at scale", RESUME)

    assert result.start is not None
    assert RESUME[result.start : result.end] == "PostgreSQL at scale"


def test_a_fabricated_quote_is_not_found() -> None:
    result = find_quote("Led a team of forty engineers", RESUME)

    assert result.found is False
    assert result.start is None


def test_case_differences_do_not_count_as_fabrication() -> None:
    """Capitalising a sentence start is typography, not invention."""
    assert find_quote("six years of python", RESUME).found is True


def test_an_empty_quote_is_not_found() -> None:
    assert find_quote("   ", RESUME).found is False


def test_normalise_maps_every_character_back_to_its_origin() -> None:
    flat, offsets = normalise("a  b\n\nc")

    assert flat == "a b c"
    assert len(offsets) == len(flat)
    assert "a  b\n\nc"[offsets[-1]] == "c"


# --- Weighted scoring (layer 3) ---


def test_a_perfect_candidate_scores_exactly_100() -> None:
    criteria = (
        VerifiedCriterion("Python", True, 5, 60, "", ()),
        VerifiedCriterion("Postgres", True, 5, 40, "", ()),
    )

    assert weighted_score(criteria) == Decimal("100.00")


def test_the_weights_decide_the_score_not_the_model() -> None:
    criteria = (
        VerifiedCriterion("Python", True, 5, 60, "", ()),
        VerifiedCriterion("Postgres", True, 0, 40, "", ()),
    )

    assert weighted_score(criteria) == Decimal("60.00")


def test_the_score_is_computed_by_hand_the_same_way() -> None:
    result = verify(_output(), RESUME, WEIGHTS)

    expected = Decimal(4) / 5 * 60 + Decimal(3) / 5 * 40
    assert result.overall_score == expected.quantize(Decimal("0.01"))
    assert result.overall_score == Decimal("72.00")


# --- Review flags ---


def test_a_clean_evaluation_needs_no_review() -> None:
    result = verify(_output(), RESUME, WEIGHTS)

    assert result.needs_human_review is False
    assert result.review_reasons == ()


def test_a_fabricated_quote_flags_the_evaluation() -> None:
    output = _output(
        criteria=[
            {
                "criterion_name": "Python",
                "score": 5,
                "justification": "Invented.",
                "evidence": ["Led a team of forty engineers"],
            },
            {
                "criterion_name": "Postgres",
                "score": 3,
                "justification": "",
                "evidence": ["PostgreSQL at scale"],
            },
        ]
    )

    result = verify(output, RESUME, WEIGHTS)

    assert result.needs_human_review is True
    assert any("not found verbatim" in reason for reason in result.review_reasons)


def test_a_criterion_the_rubric_does_not_have_flags_the_evaluation() -> None:
    output = _output(
        criteria=[
            {
                "criterion_name": "Charisma",
                "score": 5,
                "justification": "",
                "evidence": [],
            },
            {
                "criterion_name": "Postgres",
                "score": 3,
                "justification": "",
                "evidence": [],
            },
        ]
    )

    result = verify(output, RESUME, WEIGHTS)

    assert result.needs_human_review is True
    assert any("not in the rubric" in reason for reason in result.review_reasons)
    # An unmatched criterion carries no weight, so it cannot lift the score.
    assert result.overall_score == Decimal("24.00")


def test_a_skipped_rubric_criterion_flags_the_evaluation() -> None:
    output = _output(
        criteria=[{"criterion_name": "Python", "score": 5, "justification": "", "evidence": []}]
    )

    result = verify(output, RESUME, WEIGHTS)

    assert result.needs_human_review is True
    assert any("did not score" in reason for reason in result.review_reasons)


# --- Against the recorded responses ---


@pytest.mark.parametrize("name", ["strong_candidate", "weak_candidate", "injected_candidate"])
def test_every_quote_the_model_actually_produced_is_verifiable(name: str) -> None:
    """If the model paraphrases in practice, the check is worthless. Measure it."""
    fixture = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    output = EvaluationOutput.model_validate(fixture["output"])

    result = verify(output, str(fixture["resume_text"]), WEIGHTS)

    unverified = [q.quote for c in result.criteria for q in c.quotes if not q.found]
    assert unverified == [], f"{name}: model quoted text that is not in the résumé"
