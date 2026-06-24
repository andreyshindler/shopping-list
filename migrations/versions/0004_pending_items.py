"""add pending (carried-over) items

Revision ID: 0004_pending_items
Revises: 0003_user_language
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_pending_items"
down_revision = "0003_user_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pending_items_user_id", "pending_items", ["user_id"])
    op.create_index("ix_pending_items_normalized_name", "pending_items", ["normalized_name"])


def downgrade() -> None:
    op.drop_table("pending_items")
