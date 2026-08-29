"""Give the demo opening its scores, without calling the model.

`seed_demo.py` uploads résumés and then asks the API to evaluate each one, which
costs money and needs a key. Continuous integration has neither, so every
candidate stayed unscored and the panel had nothing to rank — which is exactly
what the browser journeys are there to check.

So the scores are written here instead. They are the ones recorded from real
`gpt-5.6-luna` runs in `tests/golden/comparison.json`; the justifications and the
quoted evidence are **assembled from sentences taken out of each résumé**, not
model output. That distinction matters and is why this lives in `scripts/` and
not in the fixtures: it makes the panel look like a working panel, and it is not
evidence of how the model behaves. Nothing here may ever be cited as a
measurement.

Quotes are lifted verbatim from the stored visible text, so verification finds
them and the panel's evidence links point at real spans.

    python scripts/seed_evaluations.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.schema import CriterionAssessment, EvaluationOutput
from app.db.models import Application, JobOpening
from app.db.session import SessionLocal
from app.services.evaluation import persist_evaluation

GOLDEN = Path(__file__).resolve().parent.parent / "tests" / "golden" / "comparison.json"
MODEL = "gpt-5.6-luna"
SENTENCE = re.compile(r"[^.\n]{40,180}\.")


def sentences(text: str) -> list[str]:
    """Whole sentences long enough to be worth quoting, in document order."""
    return [match.group(0).strip() for match in SENTENCE.finditer(text)]


def build(scores: dict[str, int], resume_text: str, name: str) -> EvaluationOutput:
    quotes = sentences(resume_text)
    criteria = []
    for index, (criterion, score) in enumerate(scores.items()):
        chosen = quotes[index % len(quotes) :][:1] if quotes else []
        criteria.append(
            CriterionAssessment(
                criterion_name=criterion,
                score=score,
                justification=(
                    f"Scored {score} of 5 on {criterion.lower()}, from the passage quoted below."
                ),
                evidence=chosen,
            )
        )
    met = all(score >= 3 for score in scores.values())
    return EvaluationOutput(
        criteria=criteria,
        relevant_years_experience=float(min(12, 3 + sum(scores.values()))),
        mandatory_requirements_met=met,
        missing_requirements=[] if met else ["SQL and data modelling"],
        risks=[],
        detected_skills=["SQL", "dbt", "experimentation"],
        summary=(
            f"{name} is scored against the rubric with the passages quoted beside each criterion."
        ),
    )


def main() -> int:
    recorded = json.loads(GOLDEN.read_text(encoding="utf-8"))[MODEL]

    with SessionLocal() as session:
        opening = session.scalar(select(JobOpening).where(JobOpening.slug == "data-analyst-demo"))
        if opening is None:
            print("no data-analyst-demo opening; run seed_demo.py first")
            return 1

        applications = session.scalars(
            select(Application)
            .where(Application.job_opening_id == opening.id)
            .options(
                selectinload(Application.candidate),
                selectinload(Application.resume),
                selectinload(Application.evaluation),
            )
        ).all()

        written = 0
        for application in applications:
            if application.evaluation is not None or application.resume is None:
                continue
            key = application.candidate.email.split("@")[0]
            runs = recorded.get(key)
            if not runs:
                print(f"  no recorded scores for {key}")
                continue

            output = build(
                runs[0]["criteria"],
                application.resume.visible_text,
                application.candidate.full_name,
            )
            persist_evaluation(session, application, output)
            written += 1
            print(f"  scored {application.candidate.full_name}")

        session.commit()

    print(f"\n{written} evaluation(s) written, none of them from the model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
