import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.db.models import Application, Criterion, JobOpening, ShareLink
from app.db.types import DecisionKind, IntegrityVerdict
from app.ingest import render
from app.schemas.panel import CriterionScoreOut, EvidenceOut
from app.schemas.sharing import (
    ShareCreate,
    ShareCreated,
    SharedCandidate,
    SharedView,
    ShareLinkOut,
)
from app.services import sharing

router = APIRouter(prefix="/api/v1", tags=["sharing"])

# Everything served through a share token carries this, because a shared
# shortlist must never end up in a search index.
NOINDEX = {"X-Robots-Tag": "noindex, nofollow, noarchive"}


@router.post(
    "/openings/{opening_id}/share",
    response_model=ShareCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_share(
    opening_id: uuid.UUID, payload: ShareCreate, session: SessionDep, user: CurrentUser
) -> ShareCreated:
    opening = session.get(JobOpening, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")

    issued = sharing.create(
        session,
        opening,
        created_by=user.email,
        scope=payload.scope,
        label=payload.label,
        lifetime=timedelta(days=payload.days),
    )
    session.commit()
    return ShareCreated(
        link=ShareLinkOut.model_validate(issued.link),
        url_path=f"/shared/{issued.token}",
    )


@router.get("/openings/{opening_id}/share", response_model=list[ShareLinkOut])
def list_shares(opening_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> list[ShareLinkOut]:
    return [ShareLinkOut.model_validate(link) for link in sharing.for_opening(session, opening_id)]


@router.delete("/share/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(link_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    link = session.get(ShareLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found.")
    sharing.revoke(session, link, user.email)
    session.commit()


# ─── Reached with the token alone. No session. ───


def _usable(session: SessionDep, token: str) -> ShareLink:
    try:
        return sharing.resolve(session, token)
    except sharing.LinkNotUsableError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/shared/{token}", response_model=SharedView)
def shared_view(token: str, session: SessionDep, response: Response) -> SharedView:
    """The read-only view. Contact details and declined candidates are not in it."""
    link = _usable(session, token)
    response.headers.update(NOINDEX)
    response.headers["Cache-Control"] = "no-store"

    applications = sharing.visible_applications(session, link)
    criteria = {
        c.id: c
        for c in session.scalars(
            select(Criterion).where(Criterion.job_opening_id == link.job_opening_id)
        )
    }

    candidates: list[SharedCandidate] = []
    for application in applications:
        evaluation = application.evaluation
        if evaluation is None:
            continue
        scores = [
            CriterionScoreOut(
                criterion_id=criteria[score.criterion_id].id,
                criterion_name=criteria[score.criterion_id].name,
                weight=criteria[score.criterion_id].weight,
                mandatory=criteria[score.criterion_id].mandatory,
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
            for score in sorted(evaluation.scores, key=lambda s: criteria[s.criterion_id].position)
        ]
        candidates.append(
            SharedCandidate(
                id=application.id,
                name=application.candidate.full_name,
                overall_score=evaluation.overall_score,
                summary=evaluation.summary,
                relevant_years_experience=evaluation.relevant_years_experience,
                mandatory_requirements_met=evaluation.mandatory_requirements_met,
                detected_skills=list(evaluation.detected_skills),
                criteria=scores,
                resume_text=application.resume.visible_text if application.resume else "",
                page_count=application.resume.page_count if application.resume else 0,
                tampered=bool(
                    application.integrity
                    and application.integrity.verdict is not IntegrityVerdict.CLEAN
                ),
                shortlisted=bool(
                    application.decision and application.decision.kind is DecisionKind.SHORTLIST
                ),
            )
        )

    return SharedView(
        opening_title=link.opening.title,
        company_name=link.opening.company.name,
        scope=link.scope,
        expires_at=link.expires_at,
        candidates=candidates,
    )


@router.get("/shared/{token}/candidates/{application_id}/pages/{number}")
def shared_page(
    token: str, application_id: uuid.UUID, number: int, session: SessionDep
) -> Response:
    """A résumé page, but only for a candidate this link is allowed to show."""
    from pathlib import Path

    from app.core.config import get_settings

    link = _usable(session, token)
    allowed = {a.id for a in sharing.visible_applications(session, link)}
    if application_id not in allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not available.")

    application = session.get(Application, application_id)
    if application is None or application.resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not available.")

    path = Path(get_settings().uploads_dir) / application.resume.storage_path
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, detail="No longer available.")
    try:
        image = render.render_page(path, number)
    except render.PageOutOfRangeError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(
        image,
        media_type="image/png",
        headers={
            **NOINDEX,
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
