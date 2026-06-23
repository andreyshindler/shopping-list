"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("stats_token", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_stats_token", "users", ["stats_token"], unique=True)

    op.create_table(
        "lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Shopping list"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("web_token", sa.String(length=32), nullable=False),
        sa.Column("predicted_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("real_total", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_lists_user_id", "lists", ["user_id"])
    op.create_index("ix_lists_status", "lists", ["status"])
    op.create_index("ix_lists_web_token", "lists", ["web_token"], unique=True)

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("list_id", sa.Integer(), sa.ForeignKey("lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("predicted_price", sa.Float(), nullable=True),
        sa.Column("real_price", sa.Float(), nullable=True),
        sa.Column("is_bought", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bought_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_items_list_id", "items", ["list_id"])
    op.create_index("ix_items_normalized_name", "items", ["normalized_name"])
    op.create_index("ix_items_is_bought", "items", ["is_bought"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_price_history_user_id", "price_history", ["user_id"])
    op.create_index("ix_price_history_normalized_name", "price_history", ["normalized_name"])


def downgrade() -> None:
    op.drop_table("price_history")
    op.drop_table("items")
    op.drop_table("lists")
    op.drop_table("users")
