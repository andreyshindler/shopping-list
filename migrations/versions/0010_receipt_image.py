"""Add receipt photo storage to shopping lists.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_receipt_image"
down_revision = "0009_unit_choice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lists", sa.Column("receipt_image", sa.LargeBinary(), nullable=True))
    op.add_column("lists", sa.Column("receipt_mime", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("lists", "receipt_mime")
    op.drop_column("lists", "receipt_image")
