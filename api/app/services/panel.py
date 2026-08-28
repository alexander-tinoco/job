"""Reads for the HR panel.

Every query here loads what the response needs in one go. The panel shows a
whole opening at once, so a lazy relationship is a query per candidate.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Application,
    Candidate,
    Criterion,
    Evaluation,
    JobOpening,
    ResumeDocument,
)
from app.schemas.panel import (
    ApplicationDetail,
    ApplicationSummary,
    CriterionScoreOut,
    DecisionOut,
    EvidenceOut,
    HiddenSpanOut,
    IntegrityOut,
    RankedPage,
    SearchHit,
    SearchResults,
)

EXCERPT_CHARS = 220


def _loaded() -> list[object]:
    return [
        selectinload(Application.candidate),
        selectinload(Application.resume),
        selectinload(Application.integrity),
        selectinload(Application.decision),
        selectinload(Application.evaluation).selectinload(Evaluation.scores),
    ]


def _base(opening_id: uuid.UUID) -> Select[tuple[Application]]:
    return select(Application).where(Application.job_opening_id == opening_id)


def _summary(application: Application) -> ApplicationSummary:
    evaluation = application.evaluation
    integrity = application.integrity
    hidden = (
        sum(len(str(span.get("text", "")).strip()) for span in integrity.hidden_spans)
        if integrity
        else 0
    )
    return ApplicationSummary(
        id=application.id,
        candidate_name=application.candidate.full_name,
        candidate_email=application.candidate.email,
        state=application.state,
        applied_at=application.created_at,
        overall_score=evaluation.overall_score if evaluation else None,
        summary=evaluation.summary if evaluation else "",
        mandatory_requirements_met=(evaluation.mandatory_requirements_met if evaluation else None),
        integrity=integrity.verdict if integrity else None,
        hidden_text_chars=hidden,
        needs_human_review=bool(evaluation and evaluation.needs_human_review),
        decision=DecisionOut.model_validate(application.decision) if application.decision else None,
    )


def ranked(session: Session, opening: JobOpening, limit: int, offset: int) -> RankedPage:
    """Highest score first; unscored candidates after them, oldest first.

    Unscored applications are listed rather than hidden: their résumé, extracted
    text and tampering flags are available from the moment they arrive, and the
    panel should never look empty while a batch is in flight (plan §4.1).
    """
    total = int(session.scalar(select(func.count()).select_from(_base(opening.id).subquery())) or 0)
    evaluated = int(
        session.scalar(
            select(func.count())
            .select_from(Evaluation)
            .join(Application, Application.id == Evaluation.application_id)
            .where(Application.job_opening_id == opening.id)
        )
        or 0
    )

    rows = session.scalars(
        _base(opening.id)
        .outerjoin(Evaluation, Evaluation.application_id == Application.id)
        .order_by(Evaluation.overall_score.desc().nullslast(), Application.created_at)
        .limit(limit)
        .offset(offset)
        .options(*_loaded())  # type: ignore[arg-type]
    ).all()

    return RankedPage(
        opening_id=opening.id,
        opening_title=opening.title,
        total=total,
        evaluated=evaluated,
        items=[_summary(row) for row in rows],
    )


def detail(session: Session, application_id: uuid.UUID) -> ApplicationDetail | None:
    application = session.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(*_loaded(), selectinload(Application.opening))  # type: ignore[arg-type]
    )
    if application is None:
        return None

    evaluation = application.evaluation
    resume = application.resume
    integrity = application.integrity
    criteria = {
        criterion.id: criterion
        for criterion in session.scalars(
            select(Criterion).where(Criterion.job_opening_id == application.job_opening_id)
        )
    }

    scores: list[CriterionScoreOut] = []
    if evaluation is not None:
        for score in sorted(evaluation.scores, key=lambda s: criteria[s.criterion_id].position):
            criterion = criteria[score.criterion_id]
            scores.append(
                CriterionScoreOut(
                    criterion_id=criterion.id,
                    criterion_name=criterion.name,
                    weight=criterion.weight,
                    mandatory=criterion.mandatory,
                    score=score.score,
                    justification=score.justification,
                    evidence=[
                        EvidenceOut(
                            quote=str(item.get("quote", "")),
                            found=bool(item.get("found")),
                            start=item.get("start"),  # type: ignore[arg-type]
                            end=item.get("end"),  # type: ignore[arg-type]
                        )
                        for item in score.evidence
                    ],
                )
            )

    return ApplicationDetail(
        id=application.id,
        opening_id=application.job_opening_id,
        opening_title=application.opening.title,
        candidate_name=application.candidate.full_name,
        candidate_email=application.candidate.email,
        candidate_phone=application.candidate.phone,
        candidate_linkedin=application.candidate.linkedin_url,
        state=application.state,
        applied_at=application.created_at,
        consented_at=application.candidate.consented_at,
        resume_text=resume.visible_text if resume else "",
        page_count=resume.page_count if resume else 0,
        overall_score=evaluation.overall_score if evaluation else None,
        relevant_years_experience=(evaluation.relevant_years_experience if evaluation else None),
        mandatory_requirements_met=(evaluation.mandatory_requirements_met if evaluation else None),
        missing_requirements=list(evaluation.missing_requirements) if evaluation else [],
        detected_skills=list(evaluation.detected_skills) if evaluation else [],
        summary=evaluation.summary if evaluation else "",
        risks=list(evaluation.risks) if evaluation else [],
        review_flags=list(evaluation.review_flags) if evaluation else [],
        needs_human_review=bool(evaluation and evaluation.needs_human_review),
        model_id=evaluation.model_id if evaluation else None,
        prompt_version=evaluation.prompt_version if evaluation else None,
        rubric_version=evaluation.rubric_version if evaluation else None,
        criteria=scores,
        integrity=(
            IntegrityOut(
                verdict=integrity.verdict,
                hidden_spans=[
                    HiddenSpanOut(
                        text=str(span.get("text", "")),
                        reason=str(span.get("reason", "")),
                        page=_as_int(span.get("page"), default=1),
                        detail=str(span.get("detail", "")),
                    )
                    for span in integrity.hidden_spans
                ],
                matched_patterns=list(integrity.matched_patterns),
            )
            if integrity
            else None
        ),
        decision=DecisionOut.model_validate(application.decision) if application.decision else None,
    )


def search(session: Session, opening: JobOpening, query: str, limit: int) -> SearchResults:
    """Full-text search over the sanitized résumé text.

    Postgres `websearch_to_tsquery`, so HR can type quoted phrases and `-word`
    the way they would in a search box. The index is over `visible_text` only,
    so hidden text is not searchable either (plan §6, layer 1).
    """
    tsquery = func.websearch_to_tsquery("simple", query)
    rows = session.execute(
        select(
            Application, Candidate.full_name, Evaluation.overall_score, ResumeDocument.visible_text
        )
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(ResumeDocument, ResumeDocument.application_id == Application.id)
        .outerjoin(Evaluation, Evaluation.application_id == Application.id)
        .where(
            Application.job_opening_id == opening.id,
            ResumeDocument.search_vector.op("@@")(tsquery),
        )
        .order_by(Evaluation.overall_score.desc().nullslast())
        .limit(limit)
    ).all()

    hits = [
        SearchHit(
            application_id=application.id,
            candidate_name=name,
            overall_score=score,
            excerpt=_excerpt(text, query),
        )
        for application, name, score, text in rows
    ]
    return SearchResults(query=query, hits=hits)


def _as_int(value: object, default: int) -> int:
    """JSONB gives back `object`; a malformed span must not break the whole page."""
    return value if isinstance(value, int) else default


def _excerpt(text: str, query: str) -> str:
    """A window around the first matching word, so the hit is readable in the list."""
    lowered = text.lower()
    for word in (w.strip('"-') for w in query.split()):
        if not word:
            continue
        position = lowered.find(word.lower())
        if position >= 0:
            start = max(0, position - EXCERPT_CHARS // 3)
            return text[start : start + EXCERPT_CHARS].strip()
    return text[:EXCERPT_CHARS].strip()
