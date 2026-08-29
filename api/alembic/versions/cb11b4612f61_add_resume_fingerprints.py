"""add resume fingerprints

Revision ID: cb11b4612f61
Revises: 27f1acd17546
Create Date: 2026-08-28 09:15:01.924003

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cb11b4612f61"
down_revision: str | Sequence[str] | None = "27f1acd17546"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Both nullable: a résumé ingested before this existed has no fingerprint, and
    computing one requires reading its text through Python, which a migration is
    the wrong place for. `python -m app.cli backfill-fingerprints` does it.
    """
    op.add_column("resume_documents", sa.Column("text_digest", sa.String(length=64), nullable=True))
    op.add_column(
        "resume_documents",
        sa.Column("sketch", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        op.f("ix_resume_documents_text_digest"), "resume_documents", ["text_digest"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_resume_documents_text_digest"), table_name="resume_documents")
    op.drop_column("resume_documents", "sketch")
    op.drop_column("resume_documents", "text_digest")
