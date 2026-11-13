"""The fictional shop is deterministic, plausible and kept current."""

from datetime import date, datetime, timedelta

from sqlalchemy import Engine, func, select
from sqlmodel import Session

from app.models import Sale
from app.seed.catalog import CATALOG, CUSTOMERS
from app.seed.generate import LOW_STOCK, generate, seed_database, slide_to_today

END = date(2026, 11, 13)


def test_same_seed_same_shop() -> None:
    a, b = generate(END, days=10, seed=7), generate(END, days=10, seed=7)
    assert a.sales == b.sales and a.lines == b.lines
    assert generate(END, days=10, seed=8).sales != a.sales


def test_history_is_consistent() -> None:
    shop = generate(END, days=30)
    assert len(shop.products) == len(CATALOG) and len(shop.customers) == len(CUSTOMERS)
    totals: dict[int, int] = {}
    for line in shop.lines:
        totals[line["sale_id"]] = totals.get(line["sale_id"], 0) + line["line_total_xof"]
    assert all(totals[s["id"]] == s["total_xof"] for s in shop.sales)
    days = {s["sold_at"].date() for s in shop.sales}
    assert min(days) == END - timedelta(days=29) and max(days) == END
    # Nobody pays back more than they owe.
    owed: dict[int, int] = {}
    for s in shop.sales:
        if s["payment_mode"] == "credit":
            owed[s["customer_id"]] = owed.get(s["customer_id"], 0) + s["total_xof"]
    for p in shop.payments:
        owed[p["customer_id"]] -= p["amount_xof"]
    assert min(owed.values()) >= 0


def test_low_stock_products_are_under_their_level() -> None:
    shop = generate(END, days=30)
    low = {p["name"] for p in shop.products if p["stock"] <= p["reorder_level"]}
    assert set(LOW_STOCK) <= low


def test_nothing_after_until() -> None:
    until = datetime(2026, 11, 13, 12, 0)
    shop = generate(END, days=5, until=until)
    assert max(s["sold_at"] for s in shop.sales) <= until
    assert all(p["paid_at"] <= until for p in shop.payments)


def test_slide_moves_history_without_passing_now(fresh_db: Engine) -> None:
    seed_database(fresh_db, end=date(2026, 11, 1), days=5)
    now = datetime(2026, 11, 13, 9, 30)
    assert slide_to_today(fresh_db, now=now) > 0
    with Session(fresh_db) as session:
        last = session.scalar(select(func.max(Sale.sold_at)))
    assert last <= now and now - last < timedelta(days=1)
    assert slide_to_today(fresh_db, now=now) == 0
