"""Properties, checked against inputs nobody thought to write down.

The example-based tests elsewhere pin behaviour on résumés we chose. These
state what must hold for *any* input and let Hypothesis go looking for the
counterexample — which is where the interesting failures in this project live,
because the inputs are strangers' PDFs.

Four things are worth stating this way:

* quote verification, because layer 4 of the anti-injection design rests on it
  and a wrong offset would highlight the wrong sentence in front of a reviewer;
* the weighted score, because it is the number the model is forbidden to emit
  and the one that orders the ranking;
* the duplicate estimator, because it is a sampling approximation and those are
  exactly the things that hold on the examples you tried;
* normalisation, because everything above is built on it.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.ai.verify import MAX_SCORE, VerifiedCriterion, find_quote, normalise, weighted_score
from app.services import duplicates

# Résumé-shaped text: letters, digits, punctuation and every kind of whitespace,
# because the whitespace is what extraction rebuilds and what normalisation has
# to absorb.
TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd", "Po", "Zs"),
        whitelist_characters=" \n\t\r",
    ),
    min_size=0,
    max_size=400,
)
NONBLANK = TEXT.filter(lambda s: s.strip())

# Prose, for the parts that only mean anything above the shingle floor.
WORDS = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=12
    ),
    min_size=40,
    max_size=120,
).map(" ".join)


# --- Normalisation -------------------------------------------------------


@given(TEXT)
def test_every_normalised_character_maps_back_to_a_real_offset(text: str) -> None:
    """The offsets are what the panel highlights; an invalid one is a wrong span."""
    flat, offsets = normalise(text)

    assert len(flat) == len(offsets)
    assert all(0 <= offset < len(text) for offset in offsets)
    # Strictly increasing: collapsing whitespace may skip, never go back.
    assert all(b > a for a, b in zip(offsets, offsets[1:], strict=False))


@given(TEXT)
def test_normalising_twice_changes_nothing_the_second_time(text: str) -> None:
    once, _ = normalise(text)
    twice, _ = normalise(once)
    assert once == twice


# --- Quote verification --------------------------------------------------


@given(NONBLANK, st.data())
def test_a_quote_taken_from_the_resume_is_always_found(source: str, data: st.DataObject) -> None:
    """The other half of the guarantee: a real quote must never be called a fake.

    A verifier that rejected genuine quotes would send honest candidates to
    manual review and teach whoever reads the flag to ignore it.
    """
    flat, _ = normalise(source)
    assume(flat.strip())
    start = data.draw(st.integers(min_value=0, max_value=max(0, len(flat) - 1)))
    end = data.draw(st.integers(min_value=start + 1, max_value=len(flat)))
    excerpt = flat[start:end]
    assume(excerpt.strip())

    assert find_quote(excerpt, source).found


@given(NONBLANK, st.data())
def test_a_found_quote_really_sits_where_it_says_it_does(source: str, data: st.DataObject) -> None:
    """The offsets must point at the quote, not merely somewhere plausible."""
    flat, _ = normalise(source)
    assume(flat.strip())
    start = data.draw(st.integers(min_value=0, max_value=max(0, len(flat) - 1)))
    end = data.draw(st.integers(min_value=start + 1, max_value=len(flat)))
    excerpt = flat[start:end].strip()
    assume(excerpt)

    result = find_quote(excerpt, source)
    assume(result.found)
    assert result.start is not None and result.end is not None

    span, _ = normalise(source[result.start : result.end])
    assert span.lower() == excerpt.lower()


@given(TEXT)
def test_a_blank_quote_is_never_found(source: str) -> None:
    """Empty evidence is not evidence."""
    for blank in ("", "   ", "\n\t "):
        assert not find_quote(blank, source).found


@given(NONBLANK, NONBLANK)
def test_a_quote_that_is_not_there_is_reported_without_offsets(source: str, quote: str) -> None:
    result = find_quote(quote, source)
    if not result.found:
        assert result.start is None and result.end is None


# --- The weighted score --------------------------------------------------


def _criteria(draw: st.DrawFn, count: int) -> tuple[VerifiedCriterion, ...]:
    """A rubric whose weights sum to 100, as Phase 2 guarantees."""
    weights = draw(
        st.lists(st.integers(min_value=0, max_value=100), min_size=count, max_size=count)
    )
    total = sum(weights) or 1
    scaled = [w * 100 // total for w in weights]
    scaled[0] += 100 - sum(scaled)
    scores = draw(
        st.lists(st.integers(min_value=0, max_value=MAX_SCORE), min_size=count, max_size=count)
    )
    return tuple(
        VerifiedCriterion(
            criterion_name=f"c{i}",
            matched_rubric=True,
            score=score,
            weight=weight,
            justification="",
            quotes=(),
        )
        for i, (score, weight) in enumerate(zip(scores, scaled, strict=True))
    )


@st.composite
def rubrics(draw: st.DrawFn) -> tuple[VerifiedCriterion, ...]:
    return _criteria(draw, draw(st.integers(min_value=2, max_value=8)))


@given(rubrics())
def test_the_score_is_always_a_percentage(criteria: tuple[VerifiedCriterion, ...]) -> None:
    assert Decimal("0") <= weighted_score(criteria) <= Decimal("100")


@given(rubrics())
def test_a_perfect_candidate_scores_exactly_one_hundred(
    criteria: tuple[VerifiedCriterion, ...],
) -> None:
    """Weights sum to 100 by construction, so this is arithmetic, not luck."""
    perfect = tuple(
        VerifiedCriterion(
            criterion_name=c.criterion_name,
            matched_rubric=True,
            score=MAX_SCORE,
            weight=c.weight,
            justification="",
            quotes=(),
        )
        for c in criteria
    )
    assert weighted_score(perfect) == Decimal("100.00")


@given(rubrics(), st.integers(min_value=0, max_value=7))
def test_scoring_a_criterion_higher_never_lowers_the_total(
    criteria: tuple[VerifiedCriterion, ...], index: int
) -> None:
    """Monotonic, or the ranking could reward a worse candidate."""
    assume(index < len(criteria))
    target = criteria[index]
    assume(target.score < MAX_SCORE)

    raised = list(criteria)
    raised[index] = VerifiedCriterion(
        criterion_name=target.criterion_name,
        matched_rubric=True,
        score=target.score + 1,
        weight=target.weight,
        justification="",
        quotes=(),
    )

    assert weighted_score(tuple(raised)) >= weighted_score(criteria)


# --- The duplicate estimator ---------------------------------------------


@given(WORDS)
def test_a_document_is_identical_to_itself(text: str) -> None:
    sketch = duplicates.sketch(text)
    assert sketch
    assert duplicates.similarity(sketch, sketch) == 1.0


@given(WORDS, WORDS)
def test_similarity_is_symmetric_and_bounded(left: str, right: str) -> None:
    a, b = duplicates.sketch(left), duplicates.sketch(right)
    forward = duplicates.similarity(a, b)

    assert forward == duplicates.similarity(b, a)
    assert 0.0 <= forward <= 1.0


@given(WORDS)
def test_the_sketch_never_outgrows_its_cap(text: str) -> None:
    """The storage claim: 128 integers per résumé, whatever the résumé."""
    assert len(duplicates.sketch(text)) <= duplicates.SKETCH_SIZE


@given(NONBLANK)
@settings(max_examples=50)
def test_reformatting_never_changes_the_fingerprint(text: str) -> None:
    """Case, punctuation and whitespace are not a disguise."""
    shouted = text.upper().replace(" ", "   ").replace("\n", " \n\n ")
    assert duplicates.digest(shouted) == duplicates.digest(text.upper())
    assert duplicates.normalise(shouted) == duplicates.normalise(text.upper())


@given(TEXT, TEXT)
def test_equal_normalised_text_always_gives_an_equal_digest(left: str, right: str) -> None:
    if duplicates.normalise(left) == duplicates.normalise(right):
        assert duplicates.digest(left) == duplicates.digest(right)


def test_a_name_whose_lowercase_is_longer_does_not_crash_verification() -> None:
    """The counterexample Hypothesis found, kept as an example.

    `"İ".lower()` is two characters — an `i` and a combining dot — so a position
    found in the lowered text ran off an offset map built from the original.
    `find_quote` raised `IndexError` out of `verify()`, and from the batch
    collector that lost the whole tick rather than one row. A Turkish name in a
    résumé was enough.
    """
    resume = "Senior engineer İbrahim Yılmaz, İstanbul. Eight years of Python."

    located = find_quote("İbrahim Yılmaz", resume)

    assert located.found
    assert located.start is not None and located.end is not None
    assert resume[located.start : located.end] == "İbrahim Yılmaz"
