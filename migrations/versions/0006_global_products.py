"""global product catalog, variant suggestions, and user product picks

Revision ID: 0006_global_products
Revises: 0005_item_from_pending
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_global_products"
down_revision = "0005_item_from_pending"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("needs_choice", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "global_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="ILS"),
        sa.Column("store_id", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_global_products_normalized_name", "global_products", ["normalized_name"]
    )

    op.create_table(
        "item_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
    )
    op.create_index("ix_item_suggestions_item_id", "item_suggestions", ["item_id"])

    op.create_table(
        "user_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_normalized", sa.String(length=255), nullable=False),
        sa.Column("chosen_name", sa.String(length=255), nullable=False),
        sa.Column("chosen_normalized", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="ILS"),
        sa.Column("pick_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id",
            "query_normalized",
            "chosen_normalized",
            name="uq_user_product_choice",
        ),
    )
    op.create_index("ix_user_products_user_id", "user_products", ["user_id"])
    op.create_index(
        "ix_user_products_query_normalized", "user_products", ["query_normalized"]
    )

    # Postgres-only: a trigram GIN index makes the variant substring search (ILIKE
    # '%token%') fast across the whole catalog. Skipped on SQLite (used by tests).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX ix_global_products_name_trgm "
            "ON global_products USING gin (name gin_trgm_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_global_products_name_trgm")
    op.drop_table("user_products")
    op.drop_table("item_suggestions")
    op.drop_index("ix_global_products_normalized_name", table_name="global_products")
    op.drop_table("global_products")
    op.drop_column("items", "needs_choice")
