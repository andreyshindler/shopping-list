"""One-off: re-run categorize() on all items and update the DB."""

from __future__ import annotations

from app.categories import categorize
from app.db import SessionLocal
from app.models import Item


def main() -> None:
    session = SessionLocal()
    items = session.query(Item).all()
    updated = 0
    for item in items:
        new_cat = categorize(item.normalized_name)
        if new_cat != item.category:
            item.category = new_cat
            updated += 1
    session.commit()
    session.close()
    print(f"Updated {updated} / {len(items)} items.")


if __name__ == "__main__":
    main()
