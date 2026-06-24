"""Business logic shared by the Telegram bot and the web app."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import categorize
from app.models import Item, PendingItem, PriceHistory, ShoppingList, User
from app.parsing import parse_message
from app.pricing import normalize_name, predicted_price


def get_or_create_user(
    session: Session, telegram_id: int, display_name: str | None, default_currency: str
) -> User:
    user = session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(
            telegram_id=telegram_id,
            display_name=display_name,
            currency=default_currency,
        )
        session.add(user)
        session.flush()
    elif display_name and user.display_name != display_name:
        user.display_name = display_name
    return user


def create_list_from_text(session: Session, user: User, text: str) -> ShoppingList | None:
    """Parse text, categorize items, fill predicted prices, and persist a new list."""
    parsed = parse_message(text)
    if not parsed:
        return None

    shopping_list = ShoppingList(user_id=user.id)
    session.add(shopping_list)
    session.flush()

    predicted_total = 0.0
    for order, p in enumerate(parsed):
        norm = normalize_name(p.name)
        price = predicted_price(session, user.id, norm)
        if price is not None:
            predicted_total += price * p.quantity
        session.add(
            Item(
                list_id=shopping_list.id,
                raw_name=p.name,
                normalized_name=norm,
                category=categorize(norm),
                quantity=p.quantity,
                predicted_price=price,
                sort_order=order,
            )
        )

    shopping_list.predicted_total = round(predicted_total, 2)
    session.flush()
    return shopping_list


def toggle_item(session: Session, item: Item) -> Item:
    item.is_bought = not item.is_bought
    item.bought_at = datetime.now(timezone.utc) if item.is_bought else None
    return item


def end_list(session: Session, shopping_list: ShoppingList) -> list[Item]:
    """End a list early. Unbought items are saved as the user's pending items
    (deduped by normalized name) and returned so the caller can report them."""
    missing = [item for item in shopping_list.items if not item.is_bought]
    for item in missing:
        already = session.scalar(
            select(PendingItem).where(
                PendingItem.user_id == shopping_list.user_id,
                PendingItem.normalized_name == item.normalized_name,
            )
        )
        if already is None:
            session.add(
                PendingItem(
                    user_id=shopping_list.user_id,
                    raw_name=item.raw_name,
                    normalized_name=item.normalized_name,
                    category=item.category,
                    quantity=item.quantity,
                )
            )
    shopping_list.status = "ended"
    shopping_list.completed_at = datetime.now(timezone.utc)
    return missing


def add_item_from_pending(
    session: Session, shopping_list: ShoppingList, pending: PendingItem
) -> Item:
    """Append a carried-over item to a list, refreshing the predicted total."""
    price = predicted_price(session, shopping_list.user_id, pending.normalized_name)
    order = max((i.sort_order for i in shopping_list.items), default=-1) + 1
    item = Item(
        list_id=shopping_list.id,
        raw_name=pending.raw_name,
        normalized_name=pending.normalized_name,
        category=pending.category,
        quantity=pending.quantity,
        predicted_price=price,
        sort_order=order,
        from_pending=True,
    )
    session.add(item)
    if price is not None:
        shopping_list.predicted_total = round(
            (shopping_list.predicted_total or 0.0) + price * pending.quantity, 2
        )
    return item


def _recalc_predicted_total(session: Session, shopping_list: ShoppingList) -> None:
    rows = session.scalars(
        select(Item).where(Item.list_id == shopping_list.id)
    ).all()
    total = sum((i.predicted_price or 0.0) * i.quantity for i in rows)
    shopping_list.predicted_total = round(total, 2)


def discard_carryover(session: Session, user_id: int, list_id: int | None = None) -> None:
    """Clear the user's pending items and, for the given list, remove the items that
    were added from carry-over — leaving only the freshly typed items."""
    session.query(PendingItem).filter(PendingItem.user_id == user_id).delete(
        synchronize_session=False
    )
    if list_id is None:
        return
    shopping_list = session.get(ShoppingList, list_id)
    if shopping_list is None or shopping_list.user_id != user_id:
        return
    session.query(Item).filter(
        Item.list_id == list_id, Item.from_pending.is_(True)
    ).delete(synchronize_session=False)
    session.flush()
    _recalc_predicted_total(session, shopping_list)


def complete_list(
    session: Session,
    shopping_list: ShoppingList,
    real_total: float,
    item_prices: dict[int, float] | None = None,
) -> ShoppingList:
    """Mark a list completed, store real prices, and feed the price history."""
    item_prices = item_prices or {}
    currency = shopping_list.user.currency

    for item in shopping_list.items:
        price = item_prices.get(item.id)
        if price is not None:
            item.real_price = price
            session.add(
                PriceHistory(
                    user_id=shopping_list.user_id,
                    normalized_name=item.normalized_name,
                    price=price,
                    currency=currency,
                )
            )

    shopping_list.real_total = round(real_total, 2)
    shopping_list.status = "completed"
    shopping_list.completed_at = datetime.now(timezone.utc)
    return shopping_list


def list_totals(shopping_list: ShoppingList) -> dict[str, float | int]:
    """Compute live totals for a list (used by the web UI)."""
    predicted = 0.0
    bought_predicted = 0.0
    bought_count = 0
    for item in shopping_list.items:
        line = (item.predicted_price or 0.0) * item.quantity
        predicted += line
        if item.is_bought:
            bought_predicted += line
            bought_count += 1
    return {
        "predicted_total": round(predicted, 2),
        "bought_predicted_total": round(bought_predicted, 2),
        "bought_count": bought_count,
        "total_count": len(shopping_list.items),
    }
