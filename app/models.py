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
    currency: Mapped[str] = mapped_column(String(8), default="USD")
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

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")


class PriceHistory(Base):
    """Records real prices the user entered — the manual price database."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
