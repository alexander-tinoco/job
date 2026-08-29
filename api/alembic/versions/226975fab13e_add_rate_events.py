"""add rate events

Revision ID: 226975fab13e
Revises: b0145935026b
Create Date: 2026-08-28 20:43:18.750641

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "226975fab13e"
down_revision: str | Sequence[str] | None = "b0145935026b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rate_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_events")),
    )
    op.create_index(
        "ix_rate_events_scope_key_created",
        "rate_events",
        ["scope", "key", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_rate_events_scope_key_created", table_name="rate_events")
    op.drop_table("rate_events")
