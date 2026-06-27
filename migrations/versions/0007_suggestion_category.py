"""add category to item_suggestions (group the variant picker by category)

Revision ID: 0007_suggestion_category
Revises: 0006_global_products
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_suggestion_category"
down_revision = "0006_global_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "item_suggestions",
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Other"),
    )


def downgrade() -> None:
    op.drop_column("item_suggestions", "category")
