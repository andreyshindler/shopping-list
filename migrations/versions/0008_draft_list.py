"""Add is_draft to shopping lists.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_draft_list"
down_revision = "0007_suggestion_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lists",
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("lists", "is_draft")
