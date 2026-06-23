"""Web routes and JSON API endpoints."""

from __future__ import annotations

from collections import OrderedDict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import CATEGORY_ORDER
from app.db import get_session
from app.models import Item, ShoppingList, User
from app.services import complete_list, list_totals, toggle_item
from app.stats import get_stats

router = APIRouter()


def _templates():
    from app.web.main import templates

    return templates


def _get_list(session: Session, token: str) -> ShoppingList:
    sl = session.scalar(select(ShoppingList).where(ShoppingList.web_token == token))
    if sl is None:
        raise HTTPException(status_code=404, detail="List not found")
    return sl


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
        },
    )


@router.post("/api/items/{item_id}/toggle")
def api_toggle_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    toggle_item(session, item)
    session.commit()
    sl = item.shopping_list
    totals = list_totals(sl)
    return JSONResponse(
        {
            "id": item.id,
            "is_bought": item.is_bought,
            "all_bought": totals["bought_count"] == totals["total_count"],
            "totals": totals,
        }
    )


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
        {"user": user, "summary": summary, "max_month": max_month or 1.0},
    )
