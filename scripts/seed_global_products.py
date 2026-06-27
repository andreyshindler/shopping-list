"""Dev helper: seed global_products with a few sample rows for local testing.

Lets you exercise the variant picker without running the live Shufersal scrape.
Run inside the app container:

    docker compose run --rm web python scripts/seed_global_products.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running by path (python scripts/seed_global_products.py): put the repo root,
# not the scripts/ dir, on sys.path so "app" is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import GlobalProduct  # noqa: E402
from app.pricing import normalize_name  # noqa: E402

SAMPLES: list[tuple[str, float]] = [
    # Ambiguous: typing "פלפל" should offer these variants.
    ("פלפל אדום ארוז", 12.9),
    ("פלפל אדום 500 גרם", 10.5),
    ("פלפל צהוב ארוז", 14.9),
    ("פלפל ירוק", 8.9),
    # Single match: "חלב" just gets a price, no picker.
    ("חלב תנובה 3% 1 ליטר", 6.6),
    # Ambiguous: "לחם".
    ("לחם אחיד פרוס", 7.2),
    ("לחם מלא פרוס", 9.4),
]


def main() -> None:
    with session_scope() as session:
        session.execute(delete(GlobalProduct))
        session.bulk_save_objects(
            [
                GlobalProduct(name=name, normalized_name=normalize_name(name), price=price)
                for name, price in SAMPLES
            ]
        )
    print(f"Seeded {len(SAMPLES)} sample products into global_products.")


if __name__ == "__main__":
    main()
