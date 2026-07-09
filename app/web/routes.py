"""Web routes and JSON API endpoints."""

from __future__ import annotations

from collections import OrderedDict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import requests as _requests

from app.categories import CATEGORY_ORDER
from app.config import get_settings as _get_settings
from app.db import get_session
from app.models import Item, ItemSuggestion, ShoppingList, User
from app.services import (
    complete_list,
    end_list,
    list_totals,
    resolve_custom_variant,
    resolve_variant,
    toggle_item,
)
from app.stats import get_stats
from app.web.i18n import CATEGORY_LABELS, i18n_context, normalize_lang

router = APIRouter()


def _templates():
    from app.web.main import templates

    return templates


def _get_list(session: Session, token: str) -> ShoppingList:
    sl = session.scalar(select(ShoppingList).where(ShoppingList.web_token == token))
    if sl is None:
        raise HTTPException(status_code=404, detail="List not found")
    return sl


def _get_item(session: Session, token: str, item_id: int) -> Item:
    """Fetch an item, verifying it belongs to the list named by ``token``.

    The token is the access capability for the list; checking membership here
    prevents tampering with another list's items by guessing sequential item ids.
    """
    sl = _get_list(session, token)
    item = session.get(Item, item_id)
    if item is None or item.list_id != sl.id:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def _grouped_items(shopping_list: ShoppingList) -> "OrderedDict[str, list[Item]]":
    """Group not-yet-bought items by category in display order."""
    groups: OrderedDict[str, list[Item]] = OrderedDict()
    for category in CATEGORY_ORDER:
        members = [
            i for i in shopping_list.items if not i.is_bought and i.category == category
        ]
        if members:
            groups[category] = members
    return groups


@router.get("/api/set-language")
def set_language(
    lang: str = "he",
    kind: str = "list",
    token: str = "",
    next: str = "/",
    session: Session = Depends(get_session),
):
    """Persist the chosen UI language on the owning user (shared with the bot)."""
    lang = normalize_lang(lang)
    if kind == "stats":
        user = session.scalar(select(User).where(User.stats_token == token))
    else:
        sl = session.scalar(select(ShoppingList).where(ShoppingList.web_token == token))
        user = sl.user if sl else None
    if user is not None:
        user.language = lang
        session.commit()
    # Only allow local redirects (avoid open-redirect via the `next` param).
    target = next if next.startswith("/") else "/"
    return RedirectResponse(url=target, status_code=303)


@router.get("/list/{token}", response_class=HTMLResponse)
def view_list(token: str, request: Request, session: Session = Depends(get_session)):
    sl = _get_list(session, token)
    bought = [i for i in sl.items if i.is_bought]
    return _templates().TemplateResponse(
        request,
        "list.html",
        {
            "list": sl,
            "currency": sl.user.currency,
            "groups": _grouped_items(sl),
            "bought": bought,
            "totals": list_totals(sl),
            **i18n_context(sl.user.language, sl.web_token, "list"),
        },
    )


@router.post("/api/lists/{token}/items/{item_id}/toggle")
def api_toggle_item(token: str, item_id: int, session: Session = Depends(get_session)):
    item = _get_item(session, token, item_id)
    toggle_item(session, item)
    sl = item.shopping_list   # load relationship while session is active
    totals = list_totals(sl)  # compute totals before commit
    session.commit()
    return JSONResponse(
        {
            "id": item.id,
            "is_bought": item.is_bought,
            "all_bought": totals["bought_count"] == totals["total_count"],
            "totals": totals,
        }
    )


@router.post("/api/lists/{token}/items/{item_id}/delete")
def api_delete_item(token: str, item_id: int, session: Session = Depends(get_session)):
    item = _get_item(session, token, item_id)
    if item.shopping_list.status != "active":
        raise HTTPException(status_code=400, detail="List is not active")
    session.delete(item)
    session.commit()
    return JSONResponse({"ok": True})


@router.post("/api/lists/{token}/items/{item_id}/choose-variant")
def api_choose_variant(
    token: str,
    item_id: int,
    suggestion_id: int = Form(...),
    session: Session = Depends(get_session),
):
    """Resolve an ambiguous item to the picked variant, then reload the list."""
    item = _get_item(session, token, item_id)
    suggestion = session.get(ItemSuggestion, suggestion_id)
    if suggestion is None or suggestion.item_id != item.id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    resolve_variant(session, item, suggestion)
    session.commit()
    # Anchor on the resolved item so the browser lands where the user was, instead of
    # at the top of the list.
    return RedirectResponse(url=f"/list/{token}#item-{item_id}", status_code=303)


@router.post("/api/lists/{token}/items/{item_id}/custom-variant")
def api_custom_variant(
    token: str,
    item_id: int,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    """Resolve an ambiguous item to a free-text product the user typed, then reload."""
    item = _get_item(session, token, item_id)
    if name.strip():
        resolve_custom_variant(session, item, name.strip())
        session.commit()
    return RedirectResponse(url=f"/list/{token}#item-{item_id}", status_code=303)


@router.post("/api/lists/{token}/complete")
async def api_complete_list(
    token: str,
    request: Request,
    real_total: float = Form(...),
    session: Session = Depends(get_session),
):
    sl = _get_list(session, token)
    # Optional per-item prices arrive as form fields named "price_<item_id>".
    form = await request.form()
    item_prices: dict[int, float] = {}
    for key, value in form.items():
        if key.startswith("price_") and str(value).strip():
            try:
                item_prices[int(key[len("price_") :])] = float(value)
            except ValueError:
                continue
    complete_list(session, sl, real_total, item_prices)
    session.commit()
    return RedirectResponse(url=f"/list/{token}", status_code=303)


@router.post("/api/lists/{token}/finish")
def api_finish_list(token: str, session: Session = Depends(get_session)):
    """End a list at any stage; unbought items are saved as pending for next time."""
    sl = _get_list(session, token)
    end_list(session, sl)
    session.commit()
    return RedirectResponse(url=f"/list/{token}", status_code=303)


@router.post("/api/lists/{token}/report-categories")
def api_report_categories(token: str, session: Session = Depends(get_session)):
    sl = _get_list(session, token)
    cfg = _get_settings()
    if not cfg.admin_telegram_id or not cfg.bot_token:
        raise HTTPException(status_code=503, detail="Reporting not configured")

    user = sl.user
    lines = [
        f"🐛 Category report from {user.display_name or user.telegram_id}",
        f"List: {sl.created_at:%Y-%m-%d} (id {sl.id})",
        "",
    ]
    cat_labels = CATEGORY_LABELS[normalize_lang(user.language)]
    by_cat: dict[str, list[str]] = {}
    for item in sorted(sl.items, key=lambda i: i.sort_order):
        by_cat.setdefault(item.category, []).append(item.raw_name)
    for cat, names in by_cat.items():
        lines.append(f"{cat_labels.get(cat, cat)}:")
        lines.extend(f"  • {n}" for n in names)
        lines.append("")

    # Send as plain text (no parse_mode): user-controlled item names must not be
    # interpreted as Markdown, which could break the message or inject formatting.
    text = "\n".join(lines)
    _requests.post(
        f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage",
        json={"chat_id": cfg.admin_telegram_id, "text": text},
        timeout=10,
    )
    return JSONResponse({"ok": True})


@router.get("/stats/{stats_token}", response_class=HTMLResponse)
def view_stats(stats_token: str, request: Request, session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.stats_token == stats_token))
    if user is None:
        raise HTTPException(status_code=404, detail="Stats not found")
    summary = get_stats(session, user.id, user.currency)
    max_month = max((p.total for p in summary.monthly), default=0.0)
    return _templates().TemplateResponse(
        request,
        "stats.html",
        {
            "user": user,
            "summary": summary,
            "max_month": max_month or 1.0,
            **i18n_context(user.language, user.stats_token, "stats"),
        },
    )
