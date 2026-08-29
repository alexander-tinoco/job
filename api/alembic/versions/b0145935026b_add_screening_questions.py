"""add screening questions

Revision ID: b0145935026b
Revises: cb11b4612f61
Create Date: 2026-08-28 20:00:18.435400

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b0145935026b"
down_revision: str | Sequence[str] | None = "cb11b4612f61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "screening_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_opening_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("expected_answer", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_opening_id"],
            ["job_openings.id"],
            name=op.f("fk_screening_questions_job_opening_id_job_openings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screening_questions")),
        sa.UniqueConstraint(
            "job_opening_id", "position", name="uq_screening_questions_opening_position"
        ),
    )
    op.create_table(
        "screening_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_screening_answers_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["screening_questions.id"],
            name=op.f("fk_screening_answers_question_id_screening_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screening_answers")),
        sa.UniqueConstraint(
            "application_id", "question_id", name="uq_screening_answers_application_question"
        ),
    )
    op.create_index(
        op.f("ix_screening_answers_application_id"),
        "screening_answers",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_screening_answers_application_id"), table_name="screening_answers")
    op.drop_table("screening_answers")
    op.drop_table("screening_questions")
