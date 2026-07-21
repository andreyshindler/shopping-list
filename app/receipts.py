"""Receipt scanning: turn a photo into structured products + prices via Claude vision.

The network call is isolated in :func:`parse_receipt` (which lazy-imports the
``anthropic`` SDK) so the pure JSON→dataclass step, :func:`extract_receipt_json`,
can be unit-tested without the SDK or a network. Matching a parsed receipt against
a shopping list and applying it live in ``app.services``.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime


class ReceiptParseError(Exception):
    """Raised when the model output can't be turned into a usable receipt."""


@dataclass
class ReceiptItem:
    name: str
    quantity: float
    price: float  # line total actually paid (already ×quantity)


@dataclass
class ReceiptData:
    items: list[ReceiptItem] = field(default_factory=list)
    store: str | None = None
    purchased_on: date | None = None
    total: float | None = None

    @property
    def computed_total(self) -> float:
        """The receipt total, falling back to the sum of line prices."""
        if self.total is not None:
            return round(self.total, 2)
        return round(sum(i.price for i in self.items), 2)


# The model is asked to return exactly this shape (see PROMPT). Product names stay in
# their original language (Hebrew) so they match what the user typed into their list.
PROMPT = (
    "You are reading a supermarket receipt. Extract the purchased line items and "
    "return ONLY a JSON object, no prose, with this exact shape:\n"
    '{"store": string|null, "date": "YYYY-MM-DD"|null, "total": number|null, '
    '"items": [{"name": string, "quantity": number, "price": number}]}\n'
    "Rules:\n"
    "- Keep each product name in its original language (usually Hebrew); do not translate.\n"
    "- `price` is the line total actually paid for that item (already multiplied by "
    "quantity), as a number in the receipt's currency.\n"
    "- `quantity` is the count or weight in kg; default 1 when not shown.\n"
    "- Skip non-product lines (totals, VAT, change, loyalty, payment method).\n"
    "- If the whole image is unreadable or not a receipt, return "
    '{"store": null, "date": null, "total": null, "items": []}.'
)


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        m = re.search(r"-?\d+(\.\d+)?", cleaned)
        if m:
            return float(m.group())
    return None


def _coerce_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _strip_code_fence(text: str) -> str:
    """Drop a leading/trailing ```json fence if the model wrapped its answer."""
    fence = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", text, re.DOTALL)
    return fence.group(1) if fence else text.strip()


def extract_receipt_json(text: str) -> ReceiptData:
    """Parse the model's text answer into a :class:`ReceiptData` (pure, testable)."""
    payload = _strip_code_fence(text)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        # Be lenient: grab the first {...} block if the model added stray text.
        block = re.search(r"\{.*\}", payload, re.DOTALL)
        if not block:
            raise ReceiptParseError("model did not return JSON") from exc
        try:
            data = json.loads(block.group())
        except json.JSONDecodeError as exc2:
            raise ReceiptParseError("model returned invalid JSON") from exc2

    if not isinstance(data, dict):
        raise ReceiptParseError("model JSON was not an object")

    items: list[ReceiptItem] = []
    for row in data.get("items") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        price = _coerce_float(row.get("price"))
        if not name or price is None:
            continue
        qty = _coerce_float(row.get("quantity")) or 1.0
        items.append(ReceiptItem(name=name, quantity=qty, price=round(price, 2)))

    store = data.get("store")
    return ReceiptData(
        items=items,
        store=str(store).strip() if store else None,
        purchased_on=_coerce_date(data.get("date")),
        total=_coerce_float(data.get("total")),
    )


def receipt_to_json(receipt: ReceiptData) -> str:
    """Serialize a receipt for the ReceiptDraft row (survives the confirm round-trip)."""
    return json.dumps(
        {
            "store": receipt.store,
            "date": receipt.purchased_on.isoformat() if receipt.purchased_on else None,
            "total": receipt.total,
            "items": [
                {"name": i.name, "quantity": i.quantity, "price": i.price}
                for i in receipt.items
            ],
        },
        ensure_ascii=False,
    )


def receipt_from_json(payload: str) -> ReceiptData:
    """Inverse of :func:`receipt_to_json`."""
    return extract_receipt_json(payload)


def parse_receipt(
    image_bytes: bytes,
    *,
    api_key: str,
    model: str,
    mime_type: str = "image/jpeg",
) -> ReceiptData:
    """Send the receipt photo to Claude vision and return the parsed items.

    Lazy-imports ``anthropic`` so importing this module (and unit-testing
    :func:`extract_receipt_json`) never requires the SDK to be installed.
    """
    if not api_key:
        raise ReceiptParseError("receipt scanning is not configured")
    try:
        import anthropic  # noqa: PLC0415  (intentional lazy import)
    except ImportError as exc:  # pragma: no cover - depends on deploy env
        raise ReceiptParseError("anthropic SDK is not installed") from exc

    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    message = client.messages.create(
        model=model,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    if not text.strip():
        raise ReceiptParseError("model returned an empty response")
    return extract_receipt_json(text)
