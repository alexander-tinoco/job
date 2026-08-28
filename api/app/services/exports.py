"""CSV export of an opening's results.

Every field is quoted through the csv module rather than joined with commas: a
candidate's summary contains commas and quotation marks, and a name can begin
with a character a spreadsheet will happily execute.
"""

from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy.orm import Session

from app.db.models import JobOpening
from app.services import panel

COLUMNS = [
    "rank",
    "candidate",
    "email",
    "score",
    "state",
    "meets_mandatory",
    "integrity",
    "needs_review",
    "decision",
    "decision_reason",
    "decided_by",
    "applied_at",
    "summary",
]

# A cell beginning with one of these is a formula to Excel and Sheets, and a
# candidate can choose their own name. Prefixing with a quote keeps it text.
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_DANGEROUS) else text


def opening_csv(session: Session, opening: JobOpening) -> str:
    page = panel.ranked(session, opening, limit=10_000, offset=0)
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(COLUMNS)

    for index, item in enumerate(page.items, start=1):
        writer.writerow(
            [
                index if item.overall_score is not None else "",
                _safe(item.candidate_name),
                _safe(item.candidate_email),
                item.overall_score if item.overall_score is not None else "",
                str(item.state),
                "" if item.mandatory_requirements_met is None else item.mandatory_requirements_met,
                str(item.integrity) if item.integrity else "",
                item.needs_human_review,
                str(item.decision.kind) if item.decision else "",
                _safe(item.decision.reason if item.decision else ""),
                _safe(item.decision.decided_by if item.decision else ""),
                item.applied_at.isoformat(),
                _safe(item.summary),
            ]
        )
    return buffer.getvalue()


def filename_for(opening_id: uuid.UUID, slug: str) -> str:
    return f"{slug or opening_id}.csv"
