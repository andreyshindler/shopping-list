"""Parse free-text shopping lists into structured items."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Leading bullet / numbering markers to strip from each line.
_BULLET_RE = re.compile(r"^\s*(?:[-*•·•]|\d+[.)])\s*")
# Lines that are URLs — skip them entirely.
_URL_RE = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
# "milk x2" / "milk x 2"
_TRAILING_X_RE = re.compile(r"\s*[xX]\s*(\d+(?:\.\d+)?)\s*$")
# "milk - 2" / "milk: 2"
_TRAILING_SEP_RE = re.compile(r"\s*[-:]\s*(\d+(?:\.\d+)?)\s*$")
# "2 milk" / "2x milk"
_LEADING_QTY_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[xX]?\s+(.+)$")


@dataclass(frozen=True)
class ParsedItem:
    name: str
    quantity: float


def _extract_quantity(text: str) -> tuple[str, float]:
    """Pull a quantity out of a single item line, returning (name, quantity)."""
    for pattern in (_TRAILING_X_RE, _TRAILING_SEP_RE):
        match = pattern.search(text)
        if match:
            return text[: match.start()].strip(), float(match.group(1))

    match = _LEADING_QTY_RE.match(text)
    if match:
        return match.group(2).strip(), float(match.group(1))

    return text.strip(), 1.0


def parse_message(text: str) -> list[ParsedItem]:
    """Turn a multi-line message into a list of items.

    Each non-empty line is treated as one item. Bullets/numbering are stripped and
    quantities are extracted from a handful of common patterns.
    """
    items: list[ParsedItem] = []
    seen: set[str] = set()

    # Allow comma-separated lists on a single line too.
    raw_lines: list[str] = []
    for line in text.splitlines():
        if "," in line and "\n" not in line:
            raw_lines.extend(part for part in line.split(","))
        else:
            raw_lines.append(line)

    for line in raw_lines:
        cleaned = _BULLET_RE.sub("", line).strip()
        if not cleaned or _URL_RE.search(cleaned):
            continue
        name, quantity = _extract_quantity(cleaned)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(ParsedItem(name=name, quantity=quantity))

    return items
