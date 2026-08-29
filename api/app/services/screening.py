"""Yes/no facts an applicant states about themselves.

The plan rules out a pre-filter that rejects candidates (§7, "Out"): it would
save cents and buy a real legal risk. So nothing in this module rejects, hides
or scores anybody. An answer is recorded as the applicant's own declaration and
shown to whoever reviews, and declining still takes a person and a reason.

That is also why `expected_answer` never reaches the public form. Telling a
candidate which answer the opening wants turns a question about a fact into a
form to be filled in correctly.
"""

from __future__ import annotations

import json
import uuid

from app.db.models import Application, JobOpening, ScreeningAnswer


class AnswerError(ValueError):
    """The answers submitted do not correspond to this opening's questions."""


def parse(raw: str | None) -> dict[uuid.UUID, bool]:
    """Read the answers off a multipart form field.

    JSON in a form field rather than repeated fields: the questions are dynamic,
    so the applicant's browser cannot name the fields in advance.
    """
    if raw is None or not raw.strip():
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnswerError("Answers must be a JSON object.") from exc
    if not isinstance(decoded, dict):
        raise AnswerError("Answers must be a JSON object.")

    answers: dict[uuid.UUID, bool] = {}
    for key, value in decoded.items():
        if not isinstance(value, bool):
            raise AnswerError("Every answer must be true or false.")
        try:
            answers[uuid.UUID(str(key))] = value
        except ValueError as exc:
            raise AnswerError("Every answer must be keyed by a question id.") from exc
    return answers


def record(application: Application, opening: JobOpening, answers: dict[uuid.UUID, bool]) -> None:
    """Attach the answers to the application, or refuse the whole set.

    Every question must be answered. A partial set would leave gaps that read on
    the panel exactly like a "no", which would put words in the applicant's
    mouth.
    """
    asked = {question.id for question in opening.screening_questions}
    if not asked:
        return

    unknown = set(answers) - asked
    if unknown:
        raise AnswerError("An answer refers to a question this opening does not ask.")
    missing = asked - set(answers)
    if missing:
        raise AnswerError("Every question on this opening must be answered.")

    application.screening_answers = [
        ScreeningAnswer(question_id=question_id, answer=answer)
        for question_id, answer in answers.items()
    ]


def unmet(application: Application) -> list[str]:
    """Questions whose answer is not the one the opening was looking for.

    A note, not a verdict: the caller shows it beside the application and
    nothing else consumes it.
    """
    return [
        answer.question.text
        for answer in application.screening_answers
        if answer.answer != answer.question.expected_answer
    ]
