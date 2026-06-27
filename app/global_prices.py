"""Matching against the shared global product catalog (``global_products``).

Used to (a) estimate a price for an item the user has never bought, and (b) offer
variant choices when a typed term is generic ("פלפל" -> "פלפל אדום", "פלפל צהוב").
"""

from __future__ import annotations

import re
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import categorize
from app.models import GlobalProduct
from app.pricing import normalize_name

# Letter runs in any script (so Hebrew words are tokenized too); skips digits/units.
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Most variant choices to surface for one item (across all categories).
_MAX_VARIANTS = 18


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _variant_key(name: str) -> str:
    """Collapse near-duplicate SKUs ("פלפל אדום 500 גרם", "פלפל אדום ארוז") to one
    variant by keeping only the leading meaningful (non-numeric) words."""
    toks = _tokens(name)
    return " ".join(toks[:2])


def variant_category(product: GlobalProduct) -> str:
    """Category for grouping a catalog variant in the picker.

    Retail SKU names lead with the product type ("ציפס פלפל" = chips, "רוטב פלפל" =
    sauce). When that leading word is a strong type signal (anything but Produce/Other)
    we trust it, so snacks and sauces get their own groups. Otherwise we use the general
    ``categorize`` — whose multi-word phrases handle cases like "פלפל שחור" (black
    pepper -> Pantry) that a produce head word ("פלפל") would otherwise hide.
    """
    tokens = _tokens(product.name)
    if tokens:
        head = categorize(tokens[0])
        if head not in ("Produce", "Other"):
            return head
    return categorize(product.normalized_name)


def find_variants(session: Session, query: str) -> list[GlobalProduct]:
    """Return distinct catalog variants whose name contains every word of ``query``.

    The ``ILIKE '%token%'`` filter (trigram-indexed) is a broad prefilter; we then
    keep only products where every query token appears as a **whole word**, so "שוקו"
    matches "שוקו לבחושׁ" but not "שוקולד" (chocolate). Matches are collapsed to one
    representative (cheapest) per variant label and returned cheapest-first, capped at
    ``_MAX_VARIANTS``. The full set across all categories is returned; the web picker
    groups them by category.
    """
    tokens = _tokens(query)
    if not tokens:
        return []
    query_tokens = set(tokens)

    stmt = select(GlobalProduct)
    for tok in tokens:
        stmt = stmt.where(GlobalProduct.name.ilike(f"%{tok}%"))
    stmt = stmt.order_by(GlobalProduct.price)

    representatives: dict[str, GlobalProduct] = {}
    for product in session.scalars(stmt):
        # Whole-word match: a query token must be a complete word in the name, not a
        # prefix of a longer one (שוקו should not bring back שוקולד).
        if not query_tokens.issubset(_tokens(product.name)):
            continue
        key = _variant_key(product.name)
        if key not in representatives:  # first seen is cheapest (ordered by price)
            representatives[key] = product
        if len(representatives) >= _MAX_VARIANTS:
            break
    return list(representatives.values())


def global_estimate(variants: list[GlobalProduct]) -> float | None:
    """A rough expected price for an unresolved item: the median of the variants."""
    prices = [v.price for v in variants if v.price is not None]
    if not prices:
        return None
    return round(median(prices), 2)


def is_ambiguous(query: str, variants: list[GlobalProduct]) -> bool:
    """True when the term is generic enough to warrant a variant picker.

    Ambiguous = at least two distinct variants and the typed term is not itself a
    specific product (a single word with no exact catalog match).
    """
    if len(variants) < 2:
        return False
    norm = normalize_name(query)
    if any(v.normalized_name == norm for v in variants):
        return False
    return len(_tokens(query)) == 1
