"""Recognise a résumé that has been seen before.

Two applications carrying the same text are not, by themselves, misconduct.
The same person applying to a second opening with the same CV is the ordinary
case, and reapplying to the *same* opening is already refused at the door. What
this exists to surface is the one arrangement a reviewer cannot spot alone:
**the same document submitted under two different identities.**

So the service reports what it observed and never what it means. Nothing here
scores, ranks or rejects anybody; a match is a note beside an application, and
the person reading it decides whether it matters.

Deterministic and free, like everything before the single AI call (plan §4).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Application, JobOpening, ResumeDocument

# Words per shingle. Long enough that ordinary phrases ("responsible for the
# team") do not collide across unrelated résumés, short enough that inserting a
# line does not disturb every window in the document.
SHINGLE_WORDS = 5

# Size of the bottom-k sketch. 128 hashes estimate Jaccard to within a few
# percent, which is far finer than the threshold needs, and costs 1 KB a résumé.
SKETCH_SIZE = 128

# Below this a document is too short to compare honestly: a handful of shingles
# makes any overlap look enormous. Roughly forty words.
MIN_SHINGLES = 36

# Two documents this close are the same document with edits. Genuinely different
# résumés, even in the same field with the same technologies, land near zero.
NEAR_THRESHOLD = 0.80

_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalise(text: str) -> str:
    """Strip everything a reformat would change and nothing a rewrite would.

    Case and punctuation carry no signal here, and keeping them would let a
    candidate defeat the check by exporting the same file from a different
    editor.
    """
    return _WORD.sub(" ", text.lower()).strip()


def digest(text: str) -> str:
    """The exact fingerprint. Equal digests mean byte-identical normalised text."""
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def _shingles(text: str) -> list[int]:
    words = normalise(text).split()
    if len(words) < SHINGLE_WORDS:
        return []
    seen: set[int] = set()
    for start in range(len(words) - SHINGLE_WORDS + 1):
        window = " ".join(words[start : start + SHINGLE_WORDS])
        seen.add(
            int.from_bytes(hashlib.blake2b(window.encode("utf-8"), digest_size=8).digest(), "big")
        )
    return sorted(seen)


def sketch(text: str) -> list[int]:
    """The smallest `SKETCH_SIZE` shingle hashes.

    A bottom-k sketch: because the hash is uniform, the smallest k hashes of a
    document are a uniform random sample of its shingles, and two documents'
    samples overlap in proportion to how much the documents do. That turns an
    expensive set comparison into 128 integers stored per résumé.
    """
    return _shingles(text)[:SKETCH_SIZE]


def similarity(left: list[int], right: list[int]) -> float:
    """Jaccard overlap of the two documents, 0.0 to 1.0.

    Comparing the sketches directly would be wrong: each is the bottom of its
    own document, so a hash may be missing from one sketch merely because that
    document had 128 smaller ones. Only the smallest k hashes of the *union* can
    be reasoned about, because for those, absence is genuine.

    A sketch shorter than the cap was never truncated — it is the document's
    whole shingle set — so when both are, the overlap is counted exactly rather
    than sampled. Estimating there would add several points of noise in exchange
    for nothing.
    """
    if not left or not right:
        return 0.0
    a, b = set(left), set(right)
    if len(left) < SKETCH_SIZE and len(right) < SKETCH_SIZE:
        return len(a & b) / len(a | b)

    k = min(len(left), len(right), SKETCH_SIZE)
    in_both = a & b
    return sum(1 for value in sorted(a | b)[:k] if value in in_both) / k


def fingerprint(resume: ResumeDocument) -> None:
    """Record both fingerprints from the sanitized text.

    The *visible* text on purpose: matching on hidden text would let a document
    be disguised from this check by the very trick the ingest layer exists to
    catch.
    """
    resume.text_digest = digest(resume.visible_text)
    resume.sketch = sketch(resume.visible_text)


def backfill(session: Session) -> int:
    """Fingerprint résumés ingested before this existed. Returns how many.

    Idempotent: only rows with nothing there are touched, so a second run costs
    one query and changes nothing.
    """
    pending = list(
        session.scalars(select(ResumeDocument).where(ResumeDocument.text_digest.is_(None)))
    )
    for resume in pending:
        fingerprint(resume)
    return len(pending)


@dataclass(frozen=True)
class Match:
    application_id: uuid.UUID
    candidate_name: str
    opening_title: str
    similarity: float
    identical: bool
    # False is the one worth a reviewer's attention: one document, two people.
    same_person: bool


def find(session: Session, application: Application) -> list[Match]:
    """Every other application in the company whose résumé is nearly this one.

    Scoped to the company because a match is only meaningful to whoever can
    already see both applications, and comparing across tenants would leak the
    existence of one client's candidates to another.
    """
    resume = application.resume
    if resume is None or not resume.sketch or len(_shingles(resume.visible_text)) < MIN_SHINGLES:
        return []

    company_id = application.opening.company_id
    others = session.scalars(
        select(Application)
        .join(Application.opening)
        .join(Application.resume)
        .where(JobOpening.company_id == company_id, Application.id != application.id)
        .options(
            selectinload(Application.candidate),
            selectinload(Application.opening),
            selectinload(Application.resume),
        )
    ).all()

    matches: list[Match] = []
    for other in others:
        their = other.resume
        if their is None or not their.sketch:
            continue
        identical = their.text_digest == resume.text_digest
        score = 1.0 if identical else similarity(resume.sketch, their.sketch)
        if score < NEAR_THRESHOLD:
            continue
        matches.append(
            Match(
                application_id=other.id,
                candidate_name=other.candidate.full_name,
                opening_title=other.opening.title,
                similarity=round(score, 3),
                identical=identical,
                same_person=other.candidate_id == application.candidate_id,
            )
        )

    # A different person first: that is the finding. The rest is history.
    return sorted(matches, key=lambda m: (m.same_person, -m.similarity))
