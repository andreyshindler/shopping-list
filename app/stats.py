"""Spend statistics aggregated by month and year."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Item, ShoppingList


@dataclass
class PeriodSpend:
    period: str  # "2026-06" or "2026"
    total: float
    trips: int


@dataclass
class TopItem:
    name: str
    count: int


@dataclass
class StatsSummary:
    currency: str
    total_spent: float
    total_trips: int
    monthly: list[PeriodSpend]
    yearly: list[PeriodSpend]
    top_items: list[TopItem]


def _period_spend(session: Session, user_id: int, fmt: str) -> list[PeriodSpend]:
    period = func.to_char(ShoppingList.completed_at, fmt)
    rows = session.execute(
        select(
            period.label("period"),
            func.coalesce(func.sum(ShoppingList.real_total), 0.0),
            func.count(ShoppingList.id),
        )
        .where(
            ShoppingList.user_id == user_id,
            ShoppingList.status == "completed",
            ShoppingList.completed_at.is_not(None),
        )
        .group_by(period)
        .order_by(period.desc())
    ).all()
    return [PeriodSpend(period=r[0], total=round(r[1], 2), trips=r[2]) for r in rows]


def get_stats(session: Session, user_id: int, currency: str) -> StatsSummary:
    """Build the full statistics summary for a user."""
    monthly = _period_spend(session, user_id, "YYYY-MM")
    yearly = _period_spend(session, user_id, "YYYY")

    total_spent = round(sum(p.total for p in yearly), 2)
    total_trips = sum(p.trips for p in yearly)

    top_rows = session.execute(
        select(Item.normalized_name, func.count(Item.id))
        .join(ShoppingList, Item.list_id == ShoppingList.id)
        .where(ShoppingList.user_id == user_id, Item.is_bought.is_(True))
        .group_by(Item.normalized_name)
        .order_by(func.count(Item.id).desc())
        .limit(10)
    ).all()
    top_items = [TopItem(name=r[0], count=r[1]) for r in top_rows]

    return StatsSummary(
        currency=currency,
        total_spent=total_spent,
        total_trips=total_trips,
        monthly=monthly,
        yearly=yearly,
        top_items=top_items,
    )



@dataclass
class Trip:
    web_token: str
    completed_at: datetime
    item_count: int
    predicted_total: float
    real_total: float

    @property
    def variance(self) -> float:
        return round(self.real_total - self.predicted_total, 2)


@dataclass
class TripGroup:
    year: int
    month: int
    total: float
    trips: list[Trip]


def get_trips(session: Session, user_id: int, month: str | None = None) -> list[TripGroup]:
    """Completed shopping trips, newest first, grouped by calendar month.

    ``month`` optionally filters to a single "YYYY-MM" period (the monthly-bar
    drilldown). Grouping is done in Python so it works on SQLite too.
    """
    lists = (
        session.query(ShoppingList)
        .filter(
            ShoppingList.user_id == user_id,
            ShoppingList.status == "completed",
            ShoppingList.completed_at.is_not(None),
        )
        .order_by(ShoppingList.completed_at.desc())
        .all()
    )
    groups: "OrderedDict[tuple[int, int], TripGroup]" = OrderedDict()
    for sl in lists:
        y, m = sl.completed_at.year, sl.completed_at.month
        if month and f"{y:04d}-{m:02d}" != month:
            continue
        trip = Trip(
            web_token=sl.web_token,
            completed_at=sl.completed_at,
            item_count=len(sl.items),
            predicted_total=round(sl.predicted_total or 0.0, 2),
            real_total=round(sl.real_total or 0.0, 2),
        )
        g = groups.get((y, m))
        if g is None:
            g = TripGroup(year=y, month=m, total=0.0, trips=[])
            groups[(y, m)] = g
        g.trips.append(trip)
        g.total = round(g.total + trip.real_total, 2)
    return list(groups.values())
