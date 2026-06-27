"""Daily job: refresh the shared global product catalog from the Shufersal feed.

Downloads PriceFull files from prices.shufersal.co.il, parses Hebrew product names
and prices, and replaces the ``global_products`` snapshot in one transaction.

Run it as:  python -m app.jobs.fetch_prices
On the VPS this is triggered by a host cron via ``docker compose run --rm price-fetch``.
"""

from __future__ import annotations

import gzip
import io
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from lxml import etree
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import session_scope
from app.models import GlobalProduct
from app.pricing import normalize_name

BASE_URL = "https://prices.shufersal.co.il"
_MAX_PAGES = 5


def make_session(insecure: bool = False) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    s.headers["Referer"] = BASE_URL + "/"
    if insecure:
        # Only for networks with TLS interception (a local proxy). Never in production.
        import urllib3

        urllib3.disable_warnings()
        s.verify = False
    else:
        try:
            import pip_system_certs.wrapt_requests  # noqa: F401
        except ImportError:
            pass  # fall back to system trust
    return s


def get_file_links(session: requests.Session, store_id: str) -> list[str]:
    """Collect the (deduplicated) downloadable price-file links for a store."""
    all_links: list[str] = []
    for page in range(1, _MAX_PAGES + 1):
        url = (
            f"{BASE_URL}/FileObject/UpdateCategory"
            f"?catID=2&storeId={store_id}&count=20&page={page}"
        )
        r = session.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        page_links = [
            a["href"]
            for a in soup.find_all("a", href=True)
            if "blob.core.windows.net" in a["href"]
            or a["href"].endswith(".gz")
            or a["href"].endswith(".xml")
        ]
        if not page_links:
            break
        all_links.extend(page_links)

    seen: set[str] = set()
    unique: list[str] = []
    for link in all_links:
        key = link.split("?")[0]
        if key not in seen:
            seen.add(key)
            unique.append(link)
    return unique


def download_and_parse(session: requests.Session, url: str) -> dict[str, float]:
    """Download one (gzipped) price file and return {product name: price}."""
    r = session.get(url, timeout=120, stream=True)
    r.raise_for_status()
    raw = r.content
    try:
        data = gzip.decompress(raw)
    except (OSError, EOFError):
        data = raw

    prices: dict[str, float] = {}
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as e:
        print(f"  XML error for {url.split('?')[0].split('/')[-1]}: {e}")
        return prices
    for item in root.iter("Item"):
        ne = item.find("ItemName")
        pe = item.find("ItemPrice")
        if ne is None or pe is None:
            continue
        try:
            name = (ne.text or "").strip()
            price = float((pe.text or "0").strip())
        except (ValueError, AttributeError):
            continue
        if name and price > 0:
            prices[name] = price
    return prices


def fetch_catalog(store_id: str, max_files: int, insecure: bool = False) -> dict[str, float]:
    """Return {product name: price} for the store's PriceFull files."""
    session = make_session(insecure)
    links = get_file_links(session, store_id)
    if not links:
        return {}
    pricefull = [link for link in links if "pricefull" in link.lower()]
    chosen = (pricefull or links)[:max_files]

    catalog: dict[str, float] = {}
    for link in chosen:
        try:
            catalog.update(download_and_parse(session, link))
        except requests.RequestException as e:
            print(f"  download failed: {e}")
    return catalog


def _snapshot(session) -> dict[str, float]:
    """Read current catalog as {name: price} before the replace."""
    rows = session.execute(select(GlobalProduct.name, GlobalProduct.price)).all()
    return {r.name: r.price for r in rows}


def _diff(
    old: dict[str, float], new_catalog: dict[str, float]
) -> list[tuple[str, float, float]]:
    """Return list of (name, old_price, new_price) for items whose price changed."""
    changed = []
    for name, new_price in new_catalog.items():
        if name in old and abs(new_price - old[name]) > 0.009:
            changed.append((name, old[name], new_price))
    return sorted(changed, key=lambda x: abs(x[2] - x[1]) / max(x[1], 0.01), reverse=True)


def _build_report(
    changed: list[tuple[str, float, float]],
    old_total: int,
    new_total: int,
    date_str: str,
) -> tuple[str, str | None]:
    """Return (telegram_caption, file_text_or_None).

    file_text is None when there are no price changes (caption-only message sent instead).
    """
    RLM = "‏"  # Right-to-Left Mark — forces RTL in Telegram messages only
    added = new_total - old_total  # rough; exact add/remove counts aren't tracked
    caption_lines = [
        f"{RLM}📊 עדכון מחירים יומי ({date_str})",
        f"{RLM}מוצרים: {new_total:,} (היה {old_total:,})",
        f"{RLM}מחירים שהשתנו: {len(changed)}",
    ]
    if added != 0:
        caption_lines.append(f"{RLM}שינוי בקטלוג: {'+' if added > 0 else ''}{added:,}")
    caption = "\n".join(caption_lines)

    if not changed:
        return caption, None

    lines = [f"שינויי מחירים — {date_str}", "=" * 48, ""]
    for name, old_p, new_p in changed:
        pct = (new_p - old_p) / old_p * 100
        sign = "+" if pct > 0 else ""
        lines.append(name)
        lines.append(f"שינוי: {old_p:.2f} ← {new_p:.2f}  ({sign}{pct:.1f}%)")
        lines.append("")

    return caption, "\n".join(lines)


def _notify_admin(
    bot_token: str, admin_id: int, caption: str, file_text: str | None, date_str: str,
    insecure: bool = False,
) -> None:
    api = f"https://api.telegram.org/bot{bot_token}"
    verify = not insecure
    try:
        if file_text:
            buf = io.BytesIO(file_text.encode("utf-8"))
            filename = f"price_changes_{date_str.replace('-', '')}.txt"
            requests.post(
                f"{api}/sendDocument",
                data={"chat_id": admin_id, "caption": caption},
                files={"document": (filename, buf, "text/plain")},
                timeout=30,
                verify=verify,
            ).raise_for_status()
        else:
            requests.post(
                f"{api}/sendMessage",
                json={"chat_id": admin_id, "text": caption},
                timeout=30,
                verify=verify,
            ).raise_for_status()
    except Exception as e:
        print(f"Failed to notify admin: {e}", file=sys.stderr)


def refresh_global_products() -> int:
    """Replace the global_products snapshot with the latest catalog. Returns row count."""
    settings = get_settings()
    catalog = fetch_catalog(
        settings.shufersal_store_id,
        settings.price_fetch_max_files,
        settings.price_fetch_insecure,
    )
    if not catalog:
        print("No products fetched; leaving the existing catalog untouched.")
        return 0

    with session_scope() as session:
        old = _snapshot(session)
        session.execute(delete(GlobalProduct))
        session.bulk_save_objects(
            [
                GlobalProduct(
                    name=name,
                    normalized_name=normalize_name(name),
                    price=price,
                    currency=settings.global_price_currency,
                    store_id=settings.shufersal_store_id,
                )
                for name, price in catalog.items()
            ]
        )

    print(f"Refreshed global_products: {len(catalog):,} products.")

    if settings.bot_token and settings.admin_telegram_id and old:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        changed = _diff(old, catalog)
        caption, file_text = _build_report(changed, len(old), len(catalog), date_str)
        print(caption)
        _notify_admin(
            settings.bot_token, settings.admin_telegram_id, caption, file_text, date_str,
            insecure=settings.price_fetch_insecure,
        )

    return len(catalog)


def main() -> int:
    try:
        refresh_global_products()
    except Exception as e:  # noqa: BLE001 — top-level job guard
        print(f"price fetch failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
