"""Deterministic generator of the fictional shop's history (products, receipts, credits).

Everything is invented: `generate()` returns plain rows, `seed_database()` writes them.
The same seed always gives the same shop, so a demo can be replayed identically.
"""

import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import Engine, func, insert, select, text
from sqlmodel import Session

from app.models import CreditPayment, Customer, Product, Sale, SaleLine
from app.seed.catalog import CATALOG, CUSTOMERS, CatalogItem

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 120
DEFAULT_SEED = 2026
TICKETS_PER_DAY = 30
# Products left under their reorder level, so that "what must I buy again?" has an answer.
LOW_STOCK = ("Lait en poudre", "Bouillon cube", "Huile (bidon de 5 L)", "Charbon", "Thé vert")
# Share of customers who often buy on credit, and how often they do.
CREDIT_HEAVY_SHARE = 0.3
CREDIT_HEAVY_RATE = 0.45
CREDIT_LIGHT_RATE = 0.06


@dataclass
class GeneratedShop:
    products: list[dict[str, object]] = field(default_factory=list)
    customers: list[dict[str, object]] = field(default_factory=list)
    sales: list[dict[str, object]] = field(default_factory=list)
    lines: list[dict[str, object]] = field(default_factory=list)
    payments: list[dict[str, object]] = field(default_factory=list)


def _quantity(rng: random.Random, item: CatalogItem) -> float:
    low, high, step = item.qty
    steps = int(round((high - low) / step))
    return low + step * rng.randint(0, steps)


def _tickets_for(day: date, rng: random.Random) -> int:
    factor = 1.0
    if day.weekday() >= 5:  # weekend
        factor *= 1.25
    if day.day >= 27 or day.day <= 4:  # wages are paid around the end of the month
        factor *= 1.3
    return max(5, round(TICKETS_PER_DAY * factor * rng.uniform(0.8, 1.2)))


def _ticket_time(day: date, rng: random.Random) -> datetime:
    # Morning (bread, breakfast) and evening (dinner) rushes, quieter afternoon.
    hour = rng.choices(
        range(7, 23),
        weights=[8, 9, 7, 5, 5, 6, 6, 4, 4, 5, 7, 9, 10, 8, 5, 3],
    )[0]
    return datetime.combine(day, time(hour, rng.randint(0, 59), rng.randint(0, 59)))


def _round_to(amount: float, step: int) -> int:
    return max(step, int(round(amount / step)) * step)


def generate(
    end: date,
    days: int = DEFAULT_DAYS,
    seed: int = DEFAULT_SEED,
    until: datetime | None = None,
) -> GeneratedShop:
    """Build `days` days of history ending on `end` (included).

    `until` drops what would happen later than that moment, so that "today" never
    contains receipts from hours that have not come yet.
    """
    rng = random.Random(seed)
    shop = GeneratedShop()

    for pid, item in enumerate(CATALOG, start=1):
        shop.products.append(
            {
                "id": pid,
                "name": item.name,
                "category": item.category,
                "unit": item.unit,
                "price_xof": item.price_xof,
                "cost_xof": item.cost_xof,
                "stock": 0.0,
                "reorder_level": item.reorder_level,
            }
        )
    for cid, name in enumerate(CUSTOMERS, start=1):
        shop.customers.append({"id": cid, "name": name})

    customer_ids = [c["id"] for c in shop.customers]
    heavy = set(rng.sample(customer_ids, round(len(customer_ids) * CREDIT_HEAVY_SHARE)))
    # Some regulars come far more often than others.
    visit_weights = [rng.uniform(0.5, 4.0) for _ in customer_ids]
    product_ids = [p["id"] for p in shop.products]
    product_weights = [item.weight for item in CATALOG]

    debt: dict[int, int] = defaultdict(int)
    sold_qty: dict[int, float] = defaultdict(float)
    recent_qty: dict[int, float] = defaultdict(float)
    sale_id = line_id = payment_id = 0
    start = end - timedelta(days=days - 1)

    for offset in range(days):
        day = start + timedelta(days=offset)
        times = sorted(_ticket_time(day, rng) for _ in range(_tickets_for(day, rng)))
        if until is not None:
            times = [t for t in times if t <= until]
        for sold_at in times:
            sale_id += 1
            customer_id: int | None = None
            if rng.random() < 0.45:
                customer_id = rng.choices(customer_ids, weights=visit_weights)[0]

            if customer_id is not None:
                rate = CREDIT_HEAVY_RATE if customer_id in heavy else CREDIT_LIGHT_RATE
                if rng.random() < rate:
                    mode = "credit"
                else:
                    mode = "mobile_money" if rng.random() < 0.3 else "especes"
            else:
                mode = "mobile_money" if rng.random() < 0.22 else "especes"

            n_lines = rng.choices([1, 2, 3, 4, 5], weights=[30, 30, 20, 12, 8])[0]
            chosen: list[int] = []
            while len(chosen) < n_lines:
                pid = rng.choices(product_ids, weights=product_weights)[0]
                if pid not in chosen:
                    chosen.append(pid)

            total = 0
            for pid in chosen:
                item = CATALOG[pid - 1]
                qty = _quantity(rng, item)
                line_total = round(qty * item.price_xof)
                total += line_total
                line_id += 1
                shop.lines.append(
                    {
                        "id": line_id,
                        "sale_id": sale_id,
                        "product_id": pid,
                        "quantity": qty,
                        "unit_price_xof": item.price_xof,
                        "line_total_xof": line_total,
                    }
                )
                sold_qty[pid] += qty
                if offset >= days - 14:
                    recent_qty[pid] += qty

            shop.sales.append(
                {
                    "id": sale_id,
                    "number": f"F-{sale_id:06d}",
                    "sold_at": sold_at,
                    "customer_id": customer_id,
                    "payment_mode": mode,
                    "total_xof": total,
                }
            )
            if mode == "credit" and customer_id is not None:
                debt[customer_id] += total

        # Customers pay back part of their debt, mostly when wages come in.
        payday = day.day >= 28 or day.day <= 3
        for cid in customer_ids:
            owed = debt[cid]
            if owed < 500 or rng.random() >= (0.3 if payday else 0.03):
                continue
            share = rng.uniform(0.2, 0.7) if cid in heavy else rng.uniform(0.5, 1.0)
            amount = min(owed, _round_to(owed * share, 500))
            paid_at = datetime.combine(day, time(rng.randint(8, 20), rng.randint(0, 59)))
            if until is not None and paid_at > until:
                continue
            debt[cid] -= amount
            payment_id += 1
            shop.payments.append(
                {
                    "id": payment_id,
                    "customer_id": cid,
                    "paid_at": paid_at,
                    "amount_xof": amount,
                }
            )

    for product, item in zip(shop.products, CATALOG, strict=True):
        step = item.qty[2]
        if item.name in LOW_STOCK:
            stock = item.reorder_level * rng.uniform(0.1, 0.7)
        else:
            daily = recent_qty[product["id"]] / 14
            stock = max(item.reorder_level * 1.5, daily * rng.uniform(7, 20))
        product["stock"] = round(stock / step) * step

    logger.info(
        "generated %d receipts, %d lines, %d credit payments over %d days",
        len(shop.sales),
        len(shop.lines),
        len(shop.payments),
        days,
    )
    return shop


def _reset_sequences(session: Session) -> None:
    # Rows were inserted with explicit ids: move each serial past the largest one.
    for table in ("product", "customer", "sale", "saleline", "creditpayment"):
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
            )
        )


def clear_database(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE saleline, sale, creditpayment, customer, product CASCADE"))


def seed_database(
    engine: Engine,
    end: date | None = None,
    days: int = DEFAULT_DAYS,
    seed: int = DEFAULT_SEED,
) -> GeneratedShop:
    """Write a freshly generated shop into an empty database.

    Without `end`, the history stops now: today holds only the receipts of past hours.
    """
    until = None if end else datetime.now()
    shop = generate(end or date.today(), days=days, seed=seed, until=until)
    with Session(engine) as session:
        for model, rows in (
            (Product, shop.products),
            (Customer, shop.customers),
            (Sale, shop.sales),
            (SaleLine, shop.lines),
            (CreditPayment, shop.payments),
        ):
            if rows:
                session.execute(insert(model), rows)
        _reset_sequences(session)
        session.commit()
    return shop


def is_empty(engine: Engine) -> bool:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(Product)) == 0


def slide_to_today(engine: Engine, now: datetime | None = None) -> int:
    """Move every date forward by whole days, as far as possible without the last
    receipt passing `now`. The history then always ends today or yesterday.

    Returns the number of days added (0 when the data is already current).
    """
    now = now or datetime.now()
    with Session(engine) as session:
        last = session.scalar(select(func.max(Sale.sold_at)))
        if last is None:
            return 0
        gap = (now - last).days  # whole days only: weekdays shift, hours stay real
        if gap <= 0:
            return 0
        shift = {"gap": gap}
        session.execute(
            text("UPDATE sale SET sold_at = sold_at + make_interval(days => :gap)"), shift
        )
        session.execute(
            text("UPDATE creditpayment SET paid_at = paid_at + make_interval(days => :gap)"),
            shift,
        )
        session.commit()
    logger.info("moved the fictional history forward by %d days", gap)
    return gap
