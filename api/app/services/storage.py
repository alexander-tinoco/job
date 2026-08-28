import contextlib
import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings

# A PDF must start with this. The Content-Type header is supplied by whoever is
# uploading, so a renamed executable passes it; the magic number does not.
PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 64 * 1024


class InvalidUploadError(Exception):
    """The uploaded bytes are not an acceptable résumé."""


class UploadTooLargeError(InvalidUploadError):
    pass


class NotAPdfError(InvalidUploadError):
    pass


@dataclass(frozen=True)
class StoredFile:
    relative_path: str
    size_bytes: int


async def save_resume(upload: UploadFile, application_id: str) -> StoredFile:
    """Stream the upload to disk, rejecting it mid-flight if it misbehaves.

    Both checks happen while reading, not after: accepting the whole body first
    and measuring afterwards means a 2 GB upload has already filled the disk by
    the time it is rejected.

    The filename is random rather than derived from the candidate's name, so the
    path cannot be guessed even by someone who knows the application id.
    """
    settings = get_settings()
    root = Path(settings.uploads_dir)
    directory = root / application_id
    directory.mkdir(parents=True, exist_ok=True)

    relative = f"{application_id}/{secrets.token_urlsafe(16)}.pdf"
    destination = root / relative

    size = 0
    checked_magic = False
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(CHUNK_SIZE):
                if not checked_magic:
                    if not chunk.startswith(PDF_MAGIC):
                        raise NotAPdfError("The uploaded file is not a PDF.")
                    checked_magic = True
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    limit_mb = settings.max_upload_bytes // (1024 * 1024)
                    raise UploadTooLargeError(f"Résumés must be {limit_mb} MB or smaller.")
                handle.write(chunk)
        if not checked_magic:
            raise NotAPdfError("The uploaded file is empty.")
    except InvalidUploadError:
        destination.unlink(missing_ok=True)
        _remove_if_empty(directory)
        raise

    return StoredFile(relative_path=relative, size_bytes=size)


def _remove_if_empty(directory: Path) -> None:
    # Not empty, or already gone. Either way there is nothing to clean up.
    with contextlib.suppress(OSError):
        directory.rmdir()


def delete_resume(relative_path: str) -> bool:
    """Remove a stored résumé and its per-application directory.

    A cascading delete in Postgres clears the rows and leaves the file behind.
    Retention (Phase 10) has to erase the document itself, not just the record
    of it, or "deleted after six months" is not true.
    """
    root = Path(get_settings().uploads_dir).resolve()
    # Resolved, not lexical: is_relative_to() alone accepts "uploads/../../etc",
    # because it compares strings and never collapses the "..".
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        # storage_path comes from our own code today, but a traversal here would
        # delete arbitrary files, so it is checked rather than trusted.
        raise InvalidUploadError("Refusing to delete outside the uploads directory.")
    existed = target.exists()
    target.unlink(missing_ok=True)
    _remove_if_empty(target.parent)
    return existed
