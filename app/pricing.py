"""Learned price predictions backed by the user's own purchase history."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PriceHistory

# Number of most recent records to average when predicting a price.
_HISTORY_WINDOW = 5

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Normalize an item name for matching: lowercase, de-pluralized, trimmed.

    Shared by the bot (when storing items) and pricing (when looking history up) so
    the same product always maps to the same key.
    """
    text = _WHITESPACE_RE.sub(" ", name.strip().lower())
    # Cheap singularization covering common English plural endings.
    if text.endswith("ies") and len(text) > 4:
        text = text[:-3] + "y"  # berries -> berry
    elif text.endswith("oes") and len(text) > 4:
        text = text[:-2]  # tomatoes -> tomato
    elif text.endswith(("ses", "xes", "zes", "ches", "shes")) and len(text) > 4:
        text = text[:-2]  # boxes -> box, glasses -> glass
    elif text.endswith("s") and not text.endswith("ss") and len(text) > 3:
        text = text[:-1]  # apples -> apple
    return text


def predicted_price(session: Session, user_id: int, normalized_name: str) -> float | None:
    """Predict a price as the average of the user's recent real prices for this item.

    Returns ``None`` when the item has never been purchased before.
    """
    rows = session.scalars(
        select(PriceHistory.price)
        .where(
            PriceHistory.user_id == user_id,
            PriceHistory.normalized_name == normalized_name,
        )
        .order_by(PriceHistory.recorded_at.desc())
        .limit(_HISTORY_WINDOW)
    ).all()
    if not rows:
        return None
    return round(sum(rows) / len(rows), 2)


def record_price(
    session: Session, user_id: int, normalized_name: str, price: float, currency: str
) -> None:
    """Add a real price to the history (called when a list is completed)."""
    session.add(
        PriceHistory(
            user_id=user_id,
            normalized_name=normalized_name,
            price=price,
            currency=currency,
        )
    )
