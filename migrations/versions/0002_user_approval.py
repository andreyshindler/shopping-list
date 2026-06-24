"""add user approval flag

Revision ID: 0002_user_approval
Revises: 0001_initial
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_user_approval"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Grandfather everyone who already used the bot so they aren't locked out;
    # only users created from now on go through the approval gate.
    op.execute("UPDATE users SET is_approved = true")


def downgrade() -> None:
    op.drop_column("users", "is_approved")
