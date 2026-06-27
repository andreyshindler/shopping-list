"""SQLAlchemy ORM models for the shopping list app."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """Declarative base class."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="ILS")
    language: Mapped[str] = mapped_column(String(2), default="he", server_default="he")
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    stats_token: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lists: Mapped[list[ShoppingList]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ShoppingList(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="Shopping list")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|completed
    web_token: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=_uuid)
    predicted_total: Mapped[float] = mapped_column(Float, default=0.0)
    real_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="lists")
    items: Mapped[list[Item]] = relationship(
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        order_by="Item.sort_order",
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id", ondelete="CASCADE"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(64), default="Other")
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    predicted_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    real_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_bought: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    bought_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # True when this item was added from a previous list's carried-over items.
    from_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # True while the item has unresolved variant suggestions awaiting a user pick.
    needs_choice: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")
    suggestions: Mapped[list[ItemSuggestion]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemSuggestion.id",
    )


class PendingItem(Base):
    """An item carried over from a list the user ended before buying it.

    Suggested for inclusion the next time the user starts a list.
    """

    __tablename__ = "pending_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(64), default="Other")
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceHistory(Base):
    """Records real prices the user entered — the manual price database."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="ILS")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GlobalProduct(Base):
    """A product scraped from an external price feed (Shufersal), shared by all users.

    Refreshed daily by ``app.jobs.fetch_prices``. Used as a price fallback when the
    user has no purchase history, and as the source of variant suggestions.
    """

    __tablename__ = "global_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))  # display SKU name, e.g. "פלפל אדום ארוז"
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="ILS")
    store_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ItemSuggestion(Base):
    """A variant choice offered for an ambiguous item (e.g. "פלפל" -> "פלפל אדום")."""

    __tablename__ = "item_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64), default="Other", server_default="Other")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)

    item: Mapped[Item] = relationship(back_populates="suggestions")


class UserProduct(Base):
    """A specific variant a user has picked for a generic query term.

    Seeds the user's known products and ranks variants so previously-picked ones
    appear first — it never skips the picker.
    """

    __tablename__ = "user_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query_normalized: Mapped[str] = mapped_column(String(255), index=True)
    chosen_name: Mapped[str] = mapped_column(String(255))
    chosen_normalized: Mapped[str] = mapped_column(String(255))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="ILS")
    pick_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "query_normalized", "chosen_normalized", name="uq_user_product_choice"
        ),
    )
