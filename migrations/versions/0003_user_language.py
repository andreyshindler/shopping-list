"""add per-user bot language

Revision ID: 0003_user_language
Revises: 0002_user_approval
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_user_language"
down_revision = "0002_user_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("language", sa.String(length=2), nullable=False, server_default="he"),
    )


def downgrade() -> None:
    op.drop_column("users", "language")
