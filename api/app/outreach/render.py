"""Render an outreach email from a template.

Templates are files with merge fields, versioned like the evaluator's prompts.
They are **not** written by a model, and the reason is not cost — one call per
shortlisted candidate would be five or ten per opening. A generated email
invents, and "we were impressed by your work on X" is exactly the sentence a
model produces and exactly the sentence that is wrong when X is not in the
résumé. It goes out over the client's name to someone who did not get the job
(plan §5.1.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.db.types import OutreachKind

TEMPLATE_VERSION = "v1"
_DIRECTORY = Path(__file__).parent / "templates"
_SUBJECT = re.compile(r"^SUBJECT:\s*(.+?)\n", re.DOTALL)


@dataclass(frozen=True)
class Rendered:
    subject: str
    body: str
    template_version: str


@dataclass(frozen=True)
class Merge:
    first_name: str
    role: str
    company: str
    sender_name: str


def first_name(full_name: str) -> str:
    """Enough of a name to greet someone by.

    Deliberately naive: the first word. Guessing which part of a name is the
    given name across cultures is a way to get it confidently wrong, and a
    template that greets someone by the wrong name is worse than a plain one.
    """
    cleaned = full_name.strip()
    return cleaned.split()[0] if cleaned else "there"


def load(kind: OutreachKind) -> str:
    return (_DIRECTORY / f"{kind}.{TEMPLATE_VERSION}.md").read_text(encoding="utf-8")


def render(kind: OutreachKind, merge: Merge) -> Rendered:
    raw = load(kind)
    match = _SUBJECT.match(raw)
    if match is None:
        raise ValueError(f"Template {kind} has no SUBJECT line.")

    fields = {
        "first_name": merge.first_name,
        "role": merge.role,
        "company": merge.company,
        "sender_name": merge.sender_name,
    }
    subject = match.group(1).strip().format(**fields)
    body = raw[match.end() :].strip().format(**fields)
    return Rendered(subject=subject, body=body, template_version=TEMPLATE_VERSION)
