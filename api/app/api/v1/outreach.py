import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.db.models import JobOpening, OutreachDraft
from app.db.types import OutreachState
from app.outreach import sender
from app.schemas.outreach import OutreachEdit, OutreachOut, SendRequest
from app.services import outreach

router = APIRouter(prefix="/api/v1", tags=["outreach"])


def _view(draft: OutreachDraft) -> OutreachOut:
    return OutreachOut(
        id=draft.id,
        application_id=draft.application_id,
        candidate_name=draft.application.candidate.full_name,
        candidate_email=draft.application.candidate.email,
        kind=draft.kind,
        state=draft.state,
        subject=draft.subject,
        body=draft.body,
        template_version=draft.template_version,
        approved_by=draft.approved_by,
        sent_at=draft.sent_at,
        last_error=draft.last_error,
    )


def _draft(session: SessionDep, draft_id: uuid.UUID) -> OutreachDraft:
    draft = session.get(OutreachDraft, draft_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return draft


@router.post(
    "/openings/{opening_id}/outreach",
    response_model=list[OutreachOut],
    status_code=status.HTTP_201_CREATED,
)
def draft_outreach(
    opening_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[OutreachOut]:
    """Draft an email for every decided candidate. Sends nothing."""
    opening = session.get(JobOpening, opening_id)
    if opening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    try:
        drafts = outreach.draft_all(session, opening, user.email)
    except outreach.OpeningStillOpenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    return [_view(draft) for draft in drafts]


@router.get("/openings/{opening_id}/outreach", response_model=list[OutreachOut])
def list_outreach(opening_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> list[OutreachOut]:
    return [_view(draft) for draft in outreach.for_opening(session, opening_id)]


@router.patch("/outreach/{draft_id}", response_model=OutreachOut)
def edit_draft(
    draft_id: uuid.UUID, payload: OutreachEdit, session: SessionDep, _: CurrentUser
) -> OutreachOut:
    draft = _draft(session, draft_id)
    if draft.state is OutreachState.SENT:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This message has already been sent.")
    draft.subject = payload.subject
    draft.body = payload.body
    session.commit()
    return _view(draft)


@router.post("/outreach/{draft_id}/send", response_model=OutreachOut)
def send_draft(
    draft_id: uuid.UUID, payload: SendRequest, session: SessionDep, _: CurrentUser
) -> OutreachOut:
    """The only endpoint that sends anything, and it needs a name."""
    draft = _draft(session, draft_id)
    try:
        outreach.send(session, draft, payload.approved_by.strip())
    except outreach.AlreadySentError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except sender.SendingUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except sender.SendFailedError as exc:
        session.commit()  # The failure and its reason must survive the error.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    session.commit()
    return _view(draft)
