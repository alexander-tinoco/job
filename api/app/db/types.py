import enum
import uuid


def uuid7() -> uuid.UUID:
    """Time-ordered primary key (RFC 9562 UUIDv7).

    Sequential integers would let any applicant enumerate other applications from
    the URL they receive. Random UUIDv4 fixes that but fragments the B-tree index
    on every insert. UUIDv7 is unguessable *and* monotonic, so new rows land on the
    index's hot page. Available in the standard library from Python 3.14.
    """
    return uuid.uuid7()


class ApplicationState(enum.StrEnum):
    RECEIVED = "received"
    EXTRACTED = "extracted"
    QUEUED = "queued"
    EVALUATED = "evaluated"
    ERROR = "error"


class IntegrityVerdict(enum.StrEnum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    TAMPERED = "tampered"


class OpeningStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class DecisionKind(enum.StrEnum):
    SHORTLIST = "shortlist"
    REJECT = "reject"


class QueueState(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DONE = "done"
    FAILED = "failed"
