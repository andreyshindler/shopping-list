"""scanned receipt awaiting confirmation

Revision ID: 0010_receipt_draft
Revises: 0009_unit_choice
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_receipt_draft"
down_revision = "0009_unit_choice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipt_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "list_id",
            sa.Integer(),
            sa.ForeignKey("lists.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("receipt_drafts")
