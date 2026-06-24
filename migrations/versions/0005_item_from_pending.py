"""flag items added from carried-over (pending) items

Revision ID: 0005_item_from_pending
Revises: 0004_pending_items
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_item_from_pending"
down_revision = "0004_pending_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("from_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("items", "from_pending")
