"""Business tools on a seeded shop: the figures the assistant will speak."""

from datetime import date, datetime

import pytest
from sqlalchemy import func, select
from sqlmodel import Session

from app.assistant import tools as t
from app.assistant.periods import resolve
from app.models import Sale
from app.seed.generate import LOW_STOCK
from tests.conftest import TODAY

MONTH = {"periode": "ce_mois", "date_debut": None, "date_fin": None}


@pytest.fixture
def ctx(session: Session) -> t.ToolContext:
    return t.ToolContext(session=session, today=TODAY)


def test_periods() -> None:
    first = date(2026, 1, 1)
    week = resolve("semaine_derniere", None, None, TODAY, first)
    assert (week.start.date(), week.end.date()) == (date(2026, 11, 2), date(2026, 11, 9))
    month = resolve("mois_dernier", None, None, TODAY, first)
    assert month.label == "octobre 2026" and month.end.date() == date(2026, 11, 1)
    custom = resolve("personnalisee", "2026-10-10", "2026-10-01", TODAY, first)
    assert custom.start.date() == date(2026, 10, 1) and custom.end.date() == date(2026, 10, 11)


def test_custom_period_needs_dates(ctx: t.ToolContext) -> None:
    args = t.RevenueArgs(periode="personnalisee", date_debut=None, date_fin=None, detail="aucun")
    with pytest.raises(t.ToolInputError):
        t.revenue(ctx, args)


def test_top_products_are_sorted(ctx: t.ToolContext) -> None:
    args = t.TopProductsArgs(
        **MONTH, critere="nombre_de_ventes", limite=5, categorie=None, ordre="meilleurs"
    )
    rows = t.top_products(ctx, args)["produits"]
    counts = [r["nombre_de_ventes"] for r in rows]
    assert len(rows) == 5 and counts == sorted(counts, reverse=True)
    # The two heaviest weights of the catalogue lead.
    assert rows[0]["produit"] in {"Riz brisé", "Pain"}


def test_revenue_breakdown_adds_up(ctx: t.ToolContext, session: Session) -> None:
    result = t.revenue(ctx, t.RevenueArgs(**MONTH, detail="mode_paiement"))
    assert (
        sum(r["chiffre_affaires_xof"] for r in result["lignes"]) == result["chiffre_affaires_xof"]
    )
    expected = session.scalar(
        select(func.sum(Sale.total_xof)).where(Sale.sold_at >= datetime(2026, 11, 1))
    )
    assert result["chiffre_affaires_xof"] == expected
    assert 0 < result["marge_xof"] < result["chiffre_affaires_xof"]


def test_list_sales_filters(ctx: t.ToolContext) -> None:
    args = t.ListSalesArgs(
        **MONTH, client=None, mode_paiement="credit", tri="plus_gros_montants", limite=50
    )
    result = t.list_sales(ctx, args)
    amounts = [f["montant_xof"] for f in result["factures"]]
    assert len(amounts) <= t.MAX_ROWS and amounts == sorted(amounts, reverse=True)
    assert {f["paiement"] for f in result["factures"]} == {"Crédit"}
    assert result["nombre_total"] >= len(amounts)


def test_sale_detail_reads_spoken_numbers(ctx: t.ToolContext) -> None:
    detail = t.sale_detail(ctx, t.SaleDetailArgs(numero="facture numéro 12"))
    assert detail["numero"] == "F-000012"
    assert sum(line["total_xof"] for line in detail["lignes"]) == detail["montant_xof"]
    with pytest.raises(t.ToolInputError):
        t.sale_detail(ctx, t.SaleDetailArgs(numero="F-999999"))


def test_debts_sorted_and_positive(ctx: t.ToolContext) -> None:
    result = t.debts(ctx, t.DebtsArgs(limite=5))
    owed = [c["reste_a_payer_xof"] for c in result["clients"]]
    assert owed == sorted(owed, reverse=True) and min(owed) > 0
    assert result["total_du_xof"] >= sum(owed)


def test_customer_name_from_speech(ctx: t.ToolContext) -> None:
    result = t.customer_overview(ctx, t.CustomerArgs(nom="modu diop"))
    assert result["client"] == "Modou Diop"
    with pytest.raises(t.ToolInputError, match="aucun client"):
        t.customer_overview(ctx, t.CustomerArgs(nom="Zorro"))


def test_ambiguous_product_asks_which_one(ctx: t.ToolContext) -> None:
    with pytest.raises(t.ToolInputError, match="plusieurs"):
        t.product_sales(ctx, t.ProductSalesArgs(**MONTH, produit="sucre"))
    result = t.product_sales(ctx, t.ProductSalesArgs(**MONTH, produit="Sucre en poudre"))
    assert result["produit"] == "Sucre en poudre" and result["quantite"] > 0


def test_low_stock(ctx: t.ToolContext) -> None:
    names = {p["produit"] for p in t.low_stock(ctx, t.NoArgs())["produits"]}
    assert set(LOW_STOCK) <= names


def test_matching_ignores_accents_and_case() -> None:
    names = ["Ndèye Mbaye", "Aïssatou Barry", "Thé vert"]
    assert t.best_matches("ndeye", names) == ["Ndèye Mbaye"]
    assert t.best_matches("AISSATOU", names) == ["Aïssatou Barry"]
    assert t.best_matches("the vert", names) == ["Thé vert"]
