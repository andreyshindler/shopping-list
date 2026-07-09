"""let the user pick kilograms vs units for terms sold both ways

Revision ID: 0009_unit_choice
Revises: 0008_draft_list
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_unit_choice"
down_revision = "0008_draft_list"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("weighed_override", sa.Boolean(), nullable=True))
    op.add_column("item_suggestions", sa.Column("weighed", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("item_suggestions", "weighed")
    op.drop_column("items", "weighed_override")
