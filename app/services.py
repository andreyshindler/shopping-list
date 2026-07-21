"""Business logic shared by the Telegram bot and the web app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import DUAL_CATEGORY_TERMS, UNIT_CHOICE_TERMS, categorize
from app.global_prices import (
    find_variants,
    global_estimate,
    is_ambiguous,
    is_kilo_sku,
    variant_category,
)
from app.models import (
    GlobalProduct,
    Item,
    ItemSuggestion,
    PendingItem,
    PriceHistory,
    ReceiptDraft,
    ShoppingList,
    User,
    UserProduct,
)
from app.parsing import parse_message
from app.pricing import normalize_name, predicted_price
from app.receipts import ReceiptData, ReceiptItem, receipt_from_json, receipt_to_json

# Catalog variants offered in the web picker. Kept small on purpose: the picker also
# always shows a free-text "custom product" field, so 3 + custom is enough choice.
# ``find_variants`` still scans a wider set, so the median price estimate is unaffected.
MAX_SUGGESTIONS = 3


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
        item = Item(
            list_id=shopping_list.id,
            raw_name=p.name,
            normalized_name=norm,
            category=categorize(norm),
            quantity=p.quantity,
            predicted_price=price,
            sort_order=order,
        )
        price = enrich_item_with_global(session, user.id, item)
        if price is not None:
            predicted_total += price * p.quantity
        session.add(item)

    shopping_list.predicted_total = round(predicted_total, 2)
    session.flush()
    return shopping_list


def enrich_item_with_global(session: Session, user_id: int, item: Item) -> float | None:
    """Attach variant suggestions for generic terms ("פלפל" -> "פלפל אדום"...) and fill
    the price from the shared global catalog when there's no personal history.

    The variant picker is offered for any ambiguous generic term, even one the user has
    bought before — personal history (when present) still sets the predicted price; the
    catalog price is only used as a fallback. Shared by fresh list creation and
    carry-over. Returns the item's resulting predicted price (folded into the total).
    """
    # Terms that belong to two categories: offer the categories themselves as the
    # choice, since no catalog variant can disambiguate them.
    dual = DUAL_CATEGORY_TERMS.get(item.normalized_name)
    if dual:
        item.needs_choice = True
        for category in dual:
            item.suggestions.append(
                ItemSuggestion(
                    name=item.raw_name,
                    normalized_name=item.normalized_name,
                    category=category,
                    price=item.predicted_price,
                )
            )
        return item.predicted_price

    # Terms sold both by weight and by the unit: let the user pick, pricing each option
    # from the matching catalog SKUs (per-kilo "(ק)" ones vs the rest).
    if item.normalized_name in UNIT_CHOICE_TERMS:
        catalog = find_variants(session, item.raw_name)
        per_unit = [v for v in catalog if not is_kilo_sku(v.name)]
        prices = {
            True: global_estimate(catalog, weighed=True),
            False: global_estimate(per_unit),
        }
        item.needs_choice = True
        for weighed, price in prices.items():
            item.suggestions.append(
                ItemSuggestion(
                    name=item.raw_name,
                    normalized_name=item.normalized_name,
                    category=item.category,
                    price=item.predicted_price if item.predicted_price is not None else price,
                    weighed=weighed,
                )
            )
        if item.predicted_price is None:
            item.predicted_price = prices[False]
        return item.predicted_price

    variants = find_variants(session, item.raw_name)
    if item.predicted_price is None and variants:  # no history -> fall back to catalog
        item.predicted_price = global_estimate(variants, weighed=item.weighed)
    candidates = _candidate_variants(session, user_id, item.normalized_name, variants)
    # Offer the picker for generic catalog terms, or whenever the user has prior picks
    # (including their own free-text additions) remembered for this term.
    has_prior_pick = any(c.rank > 0 for c in candidates)
    if candidates and (is_ambiguous(item.raw_name, variants) or has_prior_pick):
        item.needs_choice = True
        for c in candidates[:MAX_SUGGESTIONS]:
            item.suggestions.append(
                ItemSuggestion(
                    name=c.name,
                    normalized_name=c.normalized_name,
                    category=c.category,
                    price=c.price,
                )
            )
    return item.predicted_price


@dataclass
class _Candidate:
    name: str
    normalized_name: str
    category: str
    price: float | None
    rank: int  # pick_count for the user's prior picks (0 for catalog-only variants)


def _candidate_variants(
    session: Session, user_id: int, query_normalized: str, variants: list[GlobalProduct]
) -> list[_Candidate]:
    """Merge catalog variants with the user's remembered picks for this term.

    Catalog variants and the user's prior picks (including free-text additions, which
    aren't in the catalog) are deduped by normalized name and ordered so previously
    picked ones come first, then by price."""
    by_norm: dict[str, _Candidate] = {}
    for v in variants:
        by_norm[v.normalized_name] = _Candidate(
            v.name, v.normalized_name, variant_category(v), v.price, rank=0
        )
    picks = session.scalars(
        select(UserProduct).where(
            UserProduct.user_id == user_id,
            UserProduct.query_normalized == query_normalized,
        )
    ).all()
    for p in picks:
        existing = by_norm.get(p.chosen_normalized)
        if existing is not None:
            existing.rank = p.pick_count
        else:
            by_norm[p.chosen_normalized] = _Candidate(
                p.chosen_name, p.chosen_normalized, categorize(p.chosen_normalized),
                p.price, rank=p.pick_count,
            )
    # Personal purchase history is the source of truth: if the user has since bought a
    # candidate (e.g. a free-text product they added with no price last time), prefer
    # its real-paid price over the stale catalog/UserProduct price.
    for c in by_norm.values():
        hist = predicted_price(session, user_id, c.normalized_name)
        if hist is not None:
            c.price = hist
    return sorted(
        by_norm.values(),
        key=lambda c: (-c.rank, c.price if c.price is not None else 0.0),
    )


def get_active_draft(session: Session, user_id: int) -> ShoppingList | None:
    """Return the user's most recent active draft list, or None."""
    return session.scalar(
        select(ShoppingList)
        .where(
            ShoppingList.user_id == user_id,
            ShoppingList.status == "active",
            ShoppingList.is_draft.is_(True),
        )
        .order_by(ShoppingList.created_at.desc())
        .limit(1)
    )


def append_items_to_list(session: Session, shopping_list: ShoppingList, text: str) -> int:
    """Parse text and append new items to an existing list. Returns count of items added."""
    parsed = parse_message(text)
    if not parsed:
        return 0
    user = shopping_list.user
    max_order = max((i.sort_order for i in shopping_list.items), default=-1)
    for offset, p in enumerate(parsed):
        norm = normalize_name(p.name)
        item = Item(
            list_id=shopping_list.id,
            raw_name=p.name,
            normalized_name=norm,
            category=categorize(norm),
            quantity=p.quantity,
            predicted_price=predicted_price(session, user.id, norm),
            sort_order=max_order + 1 + offset,
        )
        enrich_item_with_global(session, user.id, item)
        session.add(item)
    session.flush()
    _recalc_predicted_total(session, shopping_list)
    return len(parsed)


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
    shopping_list.is_draft = False
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
    # Carried-over items get the same global fallback + variant picker as fresh ones.
    price = enrich_item_with_global(session, shopping_list.user_id, item)
    if price is not None:
        shopping_list.predicted_total = round(
            (shopping_list.predicted_total or 0.0) + price * pending.quantity, 2
        )
    return item


def resolve_variant(
    session: Session, item: Item, suggestion: ItemSuggestion
) -> Item:
    """Resolve an ambiguous item to the picked variant and remember the choice.

    Rewrites the item to the chosen product, clears its pending suggestions, refreshes
    the list total, and records the pick in ``user_products`` so the variant is seeded
    into the user's products and ranked first next time the same term is typed.
    """
    shopping_list = item.shopping_list
    query_normalized = item.normalized_name  # the generic term the user typed

    item.raw_name = suggestion.name
    item.normalized_name = suggestion.normalized_name
    # Trust the suggestion's category: for dual-category terms it *is* the user's pick,
    # and for catalog variants it is the grouping they saw in the picker.
    item.category = suggestion.category or categorize(suggestion.normalized_name)
    if suggestion.weighed is not None:  # kg-vs-unit pick
        item.weighed_override = suggestion.weighed
    # Prefer the user's own paid history for this exact product over the suggestion's
    # catalog price, so a product they've bought before keeps its real price.
    hist = predicted_price(session, shopping_list.user_id, suggestion.normalized_name)
    item.predicted_price = hist if hist is not None else suggestion.price
    item.needs_choice = False
    # delete-orphan cascade removes the rows on flush and empties the collection.
    item.suggestions.clear()

    _record_user_pick(
        session, shopping_list, query_normalized,
        suggestion.name, suggestion.normalized_name, suggestion.price,
    )
    session.flush()
    _recalc_predicted_total(session, shopping_list)
    return item


def resolve_custom_variant(session: Session, item: Item, name: str) -> Item:
    """Resolve an ambiguous item to a free-text product the user typed themselves.

    Works like ``resolve_variant`` but for a product that wasn't among the suggestions:
    the typed name becomes the item, its price comes from the user's history (if any),
    and the pick is remembered so it reappears as a suggestion next time."""
    shopping_list = item.shopping_list
    query_normalized = item.normalized_name  # the generic term the user typed
    norm = normalize_name(name)

    item.raw_name = name
    item.normalized_name = norm
    item.category = categorize(norm)
    item.predicted_price = predicted_price(session, shopping_list.user_id, norm)
    item.needs_choice = False
    item.suggestions.clear()

    _record_user_pick(
        session, shopping_list, query_normalized, name, norm, item.predicted_price
    )
    session.flush()
    _recalc_predicted_total(session, shopping_list)
    return item


def _record_user_pick(
    session: Session,
    shopping_list: ShoppingList,
    query_normalized: str,
    chosen_name: str,
    chosen_normalized: str,
    price: float | None,
) -> None:
    existing = session.scalar(
        select(UserProduct).where(
            UserProduct.user_id == shopping_list.user_id,
            UserProduct.query_normalized == query_normalized,
            UserProduct.chosen_normalized == chosen_normalized,
        )
    )
    now = datetime.now(timezone.utc)
    if existing is None:
        session.add(
            UserProduct(
                user_id=shopping_list.user_id,
                query_normalized=query_normalized,
                chosen_name=chosen_name,
                chosen_normalized=chosen_normalized,
                price=price,
                currency=shopping_list.user.currency,
                updated_at=now,
            )
        )
    else:
        existing.pick_count += 1
        existing.price = price
        existing.updated_at = now


def delete_lists_in_range(
    session: Session, user_id: int, start: datetime, end: datetime
) -> int:
    """Delete all of a user's lists created in [start, end). Items cascade at the DB
    level. Returns the number of lists deleted."""
    return (
        session.query(ShoppingList)
        .filter(
            ShoppingList.user_id == user_id,
            ShoppingList.created_at >= start,
            ShoppingList.created_at < end,
        )
        .delete(synchronize_session=False)
    )


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
            # Learn the price PER UNIT (per kg for weighed items): the user enters the
            # line total they paid, so divide by quantity. Multiplying by quantity next
            # time then reproduces the line total instead of squaring the quantity.
            qty = item.quantity or 1.0
            session.add(
                PriceHistory(
                    user_id=shopping_list.user_id,
                    normalized_name=item.normalized_name,
                    price=round(price / qty, 2),
                    currency=currency,
                )
            )

    shopping_list.real_total = round(real_total, 2)
    shopping_list.is_draft = False
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


# ---------------------------------------------------------------------------
# Receipt scanning: match a parsed receipt to the active list and apply it.
# ---------------------------------------------------------------------------


def get_active_list(session: Session, user_id: int) -> ShoppingList | None:
    """The user's most recent still-open (active) list — draft or confirmed."""
    return session.scalar(
        select(ShoppingList)
        .where(ShoppingList.user_id == user_id, ShoppingList.status == "active")
        .order_by(ShoppingList.created_at.desc())
        .limit(1)
    )


@dataclass
class ReceiptMatch:
    item: Item
    receipt_item: ReceiptItem


@dataclass
class ReceiptPlan:
    """Preview of what applying a receipt would do to a list."""

    matched: list[ReceiptMatch]  # list items the receipt confirms (price + bought)
    new_items: list[ReceiptItem]  # receipt lines with no matching list item
    unmatched_items: list[Item]  # list items the receipt doesn't mention


def _name_tokens(normalized: str) -> set[str]:
    return {tok for tok in normalized.split() if tok}


def _names_match(a: set[str], b: set[str]) -> bool:
    """Loose product match: identical, or one name's words contain the other's.

    Handles "חלב" vs "חלב 3%" (subset) while staying whole-word so "שוקו" never
    matches "שוקולד". Over-eager matches are caught by the user in the preview.
    """
    if not a or not b:
        return False
    return a == b or a <= b or b <= a


def match_receipt(
    session: Session, shopping_list: ShoppingList | None, receipt: ReceiptData
) -> ReceiptPlan:
    """Line up receipt items against a list's items (each list item matched once)."""
    list_items = list(shopping_list.items) if shopping_list is not None else []
    item_tokens = [(it, _name_tokens(it.normalized_name)) for it in list_items]
    consumed: set[int] = set()
    matched: list[ReceiptMatch] = []
    new_items: list[ReceiptItem] = []

    for r in receipt.items:
        rt = _name_tokens(normalize_name(r.name))
        hit = None
        for idx, (it, toks) in enumerate(item_tokens):
            if idx in consumed:
                continue
            if _names_match(rt, toks):
                hit = idx
                break
        if hit is None:
            new_items.append(r)
        else:
            consumed.add(hit)
            matched.append(ReceiptMatch(item=item_tokens[hit][0], receipt_item=r))

    unmatched = [it for i, (it, _) in enumerate(item_tokens) if i not in consumed]
    return ReceiptPlan(matched=matched, new_items=new_items, unmatched_items=unmatched)


def _receipt_datetime(receipt: ReceiptData) -> datetime:
    """The purchase timestamp: the receipt's date at midnight UTC, else now."""
    d = receipt.purchased_on
    if d is None:
        return datetime.now(timezone.utc)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _record_receipt_price(
    session: Session, user_id: int, normalized_name: str, r: ReceiptItem,
    currency: str, when: datetime,
) -> None:
    """Feed the price history with the PER-UNIT price, dated to the purchase."""
    qty = r.quantity or 1.0
    session.add(
        PriceHistory(
            user_id=user_id,
            normalized_name=normalized_name,
            price=round(r.price / qty, 2),
            currency=currency,
            recorded_at=when,
        )
    )


def apply_receipt(
    session: Session,
    shopping_list: ShoppingList,
    receipt: ReceiptData,
    plan: ReceiptPlan | None = None,
) -> ShoppingList:
    """Apply a scanned receipt: set real prices on matches, add new bought items,
    complete the list, and record prices to history dated to the purchase.

    Mirrors :func:`complete_list`'s per-unit price learning; unmatched list items are
    left untouched (not marked bought) so the list still reflects what wasn't bought.
    """
    plan = plan or match_receipt(session, shopping_list, receipt)
    currency = shopping_list.user.currency
    when = _receipt_datetime(receipt)

    for m in plan.matched:
        m.item.real_price = round(m.receipt_item.price, 2)
        m.item.is_bought = True
        m.item.bought_at = when
        _record_receipt_price(
            session, shopping_list.user_id, m.item.normalized_name,
            m.receipt_item, currency, when,
        )

    max_order = max((i.sort_order for i in shopping_list.items), default=-1)
    for r in plan.new_items:
        max_order += 1
        norm = normalize_name(r.name)
        # Append via the relationship so the in-memory items collection stays in sync
        # (both the bot summary and callers re-read shopping_list.items right after).
        shopping_list.items.append(
            Item(
                raw_name=r.name,
                normalized_name=norm,
                category=categorize(norm),
                quantity=r.quantity,
                real_price=round(r.price, 2),
                is_bought=True,
                bought_at=when,
                sort_order=max_order,
            )
        )
        _record_receipt_price(session, shopping_list.user_id, norm, r, currency, when)

    shopping_list.real_total = receipt.computed_total
    shopping_list.is_draft = False
    shopping_list.status = "completed"
    shopping_list.completed_at = when
    session.flush()
    return shopping_list


def save_receipt_draft(
    session: Session, user_id: int, list_id: int | None, receipt: ReceiptData
) -> ReceiptDraft:
    """Persist a parsed receipt awaiting the user's Confirm tap."""
    draft = ReceiptDraft(
        user_id=user_id, list_id=list_id, payload=receipt_to_json(receipt)
    )
    session.add(draft)
    session.flush()
    return draft


def load_receipt_draft(session: Session, draft_id: int, user_id: int) -> ReceiptDraft | None:
    """Fetch a receipt draft, scoped to its owner (guards against cross-user ids)."""
    draft = session.get(ReceiptDraft, draft_id)
    if draft is None or draft.user_id != user_id:
        return None
    return draft


def receipt_from_draft(draft: ReceiptDraft) -> ReceiptData:
    return receipt_from_json(draft.payload)
