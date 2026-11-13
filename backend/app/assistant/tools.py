"""Business tools the assistant calls. Every figure it speaks comes from one of these.

Each tool has a strict Pydantic input model (sent to Claude as its JSON schema) and a
function returning a JSON-serialisable dict. That dict is both the tool result read by
the model and the card drawn on screen, so what is said and what is shown always match.
"""

import difflib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlmodel import Session

from app.assistant.periods import PERIOD_HELP, Period, PeriodError, Range, resolve
from app.models import CreditPayment, Customer, Product, Sale, SaleLine

MAX_ROWS = 20

PAYMENT_LABELS = {"especes": "Espèces", "mobile_money": "Mobile money", "credit": "Crédit"}


class ToolInputError(ValueError):
    """Bad arguments: the message goes back to the model as an error tool result."""


class StrictModel(BaseModel):
    # extra="forbid" emits additionalProperties: false, required by strict tool use.
    model_config = ConfigDict(extra="forbid")


class PeriodArgs(StrictModel):
    periode: Period = Field(description=PERIOD_HELP)
    date_debut: str | None = Field(description="AAAA-MM-JJ, seulement si personnalisee")
    date_fin: str | None = Field(description="AAAA-MM-JJ, seulement si personnalisee")


@dataclass
class ToolContext:
    session: Session
    today: date

    def first_day(self) -> date:
        first = self.session.scalar(select(func.min(Sale.sold_at)))
        return first.date() if first else self.today

    def period(self, args: PeriodArgs) -> Range:
        try:
            return resolve(
                args.periode, args.date_debut, args.date_fin, self.today, self.first_day()
            )
        except PeriodError as exc:
            raise ToolInputError(str(exc)) from exc


# --- Name matching (speech-to-text output is approximate) ---


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


def best_matches(query: str, names: list[str], limit: int = 5) -> list[str]:
    """Names containing the query first, then close spellings."""
    q = normalize(query)
    if not q:
        return []
    by_norm = {normalize(n): n for n in names}
    exact = [n for norm, n in by_norm.items() if norm == q]
    if exact:
        return exact
    contained = [n for norm, n in by_norm.items() if q in norm]
    if not contained:
        words = q.split()
        contained = [n for norm, n in by_norm.items() if all(w in norm for w in words)]
    if contained:
        return sorted(contained, key=len)[:limit]
    close = difflib.get_close_matches(q, list(by_norm), n=limit, cutoff=0.6)
    return [by_norm[c] for c in close]


def _one(kind: str, query: str, names: list[str]) -> str:
    found = best_matches(query, names)
    if not found:
        raise ToolInputError(f"aucun {kind} ne correspond à « {query} »")
    if len(found) > 1 and normalize(found[0]) != normalize(query):
        raise ToolInputError(
            f"plusieurs {kind}s correspondent à « {query} » : {', '.join(found)}. "
            "Demander lequel, ou réessayer avec le nom exact."
        )
    return found[0]


def _qty(value: float) -> float | int:
    rounded = round(value, 2)
    return int(rounded) if rounded == int(rounded) else rounded


def _dt(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def _in(rng: Range) -> Any:
    return Sale.sold_at.between(rng.start, rng.end - timedelta(microseconds=1))


# --- Tools ---


class TopProductsArgs(PeriodArgs):
    critere: Literal["nombre_de_ventes", "quantite", "chiffre_affaires", "marge"] = Field(
        description=(
            "nombre_de_ventes = nombre de factures contenant le produit (sens habituel de "
            "« le plus acheté ») ; quantite = unités vendues ; chiffre_affaires ; marge"
        )
    )
    limite: int = Field(description="nombre de produits, 1 à 10")
    categorie: str | None = Field(description="filtrer sur une catégorie, sinon null")
    ordre: Literal["meilleurs", "moins_bons"] = Field(
        description="meilleurs pour les plus vendus, moins_bons pour les moins vendus"
    )


def top_products(ctx: ToolContext, args: TopProductsArgs) -> dict[str, Any]:
    rng = ctx.period(args)
    limit = min(max(args.limite, 1), 10)
    quantity = func.sum(SaleLine.quantity)
    revenue = func.sum(SaleLine.line_total_xof)
    margin = func.sum(SaleLine.line_total_xof - SaleLine.quantity * Product.cost_xof)
    receipts = func.count(func.distinct(SaleLine.sale_id))
    metric = {
        "nombre_de_ventes": receipts,
        "quantite": quantity,
        "chiffre_affaires": revenue,
        "marge": margin,
    }[args.critere]
    query = (
        select(Product.name, Product.unit, Product.category, quantity, revenue, margin, receipts)
        .join(SaleLine, SaleLine.product_id == Product.id)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .where(_in(rng))
        .group_by(Product.id)
        .order_by(metric.desc() if args.ordre == "meilleurs" else metric.asc())
        .limit(limit)
    )
    if args.categorie:
        categories = list(ctx.session.scalars(select(Product.category).distinct()))
        query = query.where(Product.category == _one("catégorie", args.categorie, categories))
    rows = [
        {
            "produit": name,
            "unite": unit,
            "categorie": category,
            "quantite": _qty(q),
            "chiffre_affaires_xof": int(rev),
            "marge_xof": round(m),
            "nombre_de_ventes": n,
        }
        for name, unit, category, q, rev, m, n in ctx.session.execute(query)
    ]
    return {"periode": rng.as_dict(), "critere": args.critere, "produits": rows}


class RevenueArgs(PeriodArgs):
    detail: Literal["aucun", "jour", "semaine", "mois", "mode_paiement", "categorie"] = Field(
        description="découpage du chiffre d'affaires ; aucun pour le total seul"
    )


def revenue(ctx: ToolContext, args: RevenueArgs) -> dict[str, Any]:
    rng = ctx.period(args)
    totals = ctx.session.execute(
        select(func.coalesce(func.sum(Sale.total_xof), 0), func.count(Sale.id)).where(_in(rng))
    ).one()
    margin = ctx.session.scalar(
        select(
            func.coalesce(
                func.sum(SaleLine.line_total_xof - SaleLine.quantity * Product.cost_xof), 0
            )
        )
        .join(Product, Product.id == SaleLine.product_id)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .where(_in(rng))
    )
    total, count = int(totals[0]), int(totals[1])
    result: dict[str, Any] = {
        "periode": rng.as_dict(),
        "chiffre_affaires_xof": total,
        "marge_xof": round(margin or 0),
        "nombre_de_factures": count,
        "panier_moyen_xof": round(total / count) if count else 0,
        "detail": args.detail,
        "lignes": [],
    }
    if args.detail in ("jour", "semaine", "mois"):
        unit = {"jour": "day", "semaine": "week", "mois": "month"}[args.detail]
        bucket = func.date_trunc(unit, Sale.sold_at)
        query = (
            select(bucket, func.sum(Sale.total_xof), func.count(Sale.id))
            .where(_in(rng))
            .group_by(bucket)
            .order_by(bucket)
        )
        result["lignes"] = [
            {"libelle": b.date().isoformat(), "chiffre_affaires_xof": int(t), "factures": n}
            for b, t, n in ctx.session.execute(query)
        ][-62:]
    elif args.detail == "mode_paiement":
        query = (
            select(Sale.payment_mode, func.sum(Sale.total_xof), func.count(Sale.id))
            .where(_in(rng))
            .group_by(Sale.payment_mode)
            .order_by(func.sum(Sale.total_xof).desc())
        )
        result["lignes"] = [
            {"libelle": PAYMENT_LABELS.get(m, m), "chiffre_affaires_xof": int(t), "factures": n}
            for m, t, n in ctx.session.execute(query)
        ]
    elif args.detail == "categorie":
        query = (
            select(Product.category, func.sum(SaleLine.line_total_xof))
            .join(SaleLine, SaleLine.product_id == Product.id)
            .join(Sale, Sale.id == SaleLine.sale_id)
            .where(_in(rng))
            .group_by(Product.category)
            .order_by(func.sum(SaleLine.line_total_xof).desc())
        )
        result["lignes"] = [
            {"libelle": c, "chiffre_affaires_xof": int(t)} for c, t in ctx.session.execute(query)
        ]
    return result


class ListSalesArgs(PeriodArgs):
    client: str | None = Field(description="nom du client, sinon null")
    mode_paiement: Literal["especes", "mobile_money", "credit"] | None = Field(
        description="filtrer sur un mode de paiement, sinon null"
    )
    tri: Literal["plus_recentes", "plus_gros_montants"]
    limite: int = Field(description="nombre de factures affichées, 1 à 20")


def _customer_names(ctx: ToolContext) -> list[str]:
    return list(ctx.session.scalars(select(Customer.name)))


def list_sales(ctx: ToolContext, args: ListSalesArgs) -> dict[str, Any]:
    rng = ctx.period(args)
    limit = min(max(args.limite, 1), MAX_ROWS)
    conditions = [_in(rng)]
    client_name = None
    if args.client:
        client_name = _one("client", args.client, _customer_names(ctx))
        conditions.append(Customer.name == client_name)
    if args.mode_paiement:
        conditions.append(Sale.payment_mode == args.mode_paiement)

    matching = (
        select(Sale.total_xof)
        .outerjoin(Customer, Customer.id == Sale.customer_id)
        .where(*conditions)
        .subquery()
    )
    count, total = ctx.session.execute(
        select(func.count(), func.coalesce(func.sum(matching.c.total_xof), 0))
    ).one()
    order = Sale.sold_at.desc() if args.tri == "plus_recentes" else Sale.total_xof.desc()
    items = func.count(SaleLine.id)
    rows = ctx.session.execute(
        select(Sale.number, Sale.sold_at, Customer.name, Sale.payment_mode, Sale.total_xof, items)
        .outerjoin(Customer, Customer.id == Sale.customer_id)
        .join(SaleLine, SaleLine.sale_id == Sale.id)
        .where(*conditions)
        .group_by(Sale.id, Customer.name)
        .order_by(order)
        .limit(limit)
    )
    return {
        "periode": rng.as_dict(),
        "client": client_name,
        "mode_paiement": PAYMENT_LABELS.get(args.mode_paiement or ""),
        "nombre_total": int(count),
        "montant_total_xof": int(total),
        "factures": [
            {
                "numero": number,
                "date": _dt(sold_at),
                "client": name,
                "paiement": PAYMENT_LABELS.get(mode, mode),
                "montant_xof": amount,
                "articles": n,
            }
            for number, sold_at, name, mode, amount, n in rows
        ],
    }


class SaleDetailArgs(StrictModel):
    numero: str = Field(description="numéro de facture, par exemple F-000123 ou 123")


def sale_detail(ctx: ToolContext, args: SaleDetailArgs) -> dict[str, Any]:
    digits = "".join(c for c in args.numero if c.isdigit())
    if not digits:
        raise ToolInputError("numéro de facture illisible")
    number = f"F-{int(digits):06d}"
    sale = ctx.session.scalar(select(Sale).where(Sale.number == number))
    if sale is None:
        raise ToolInputError(f"la facture {number} n'existe pas")
    customer = ctx.session.get(Customer, sale.customer_id) if sale.customer_id else None
    lines = ctx.session.execute(
        select(
            Product.name,
            Product.unit,
            SaleLine.quantity,
            SaleLine.unit_price_xof,
            SaleLine.line_total_xof,
        )
        .join(Product, Product.id == SaleLine.product_id)
        .where(SaleLine.sale_id == sale.id)
        .order_by(SaleLine.id)
    )
    return {
        "numero": sale.number,
        "date": _dt(sale.sold_at),
        "client": customer.name if customer else None,
        "paiement": PAYMENT_LABELS.get(sale.payment_mode, sale.payment_mode),
        "montant_xof": sale.total_xof,
        "lignes": [
            {
                "produit": name,
                "unite": unit,
                "quantite": _qty(q),
                "prix_unitaire_xof": price,
                "total_xof": total,
            }
            for name, unit, q, price, total in lines
        ],
    }


def _balances(ctx: ToolContext) -> dict[int, dict[str, Any]]:
    credit = dict(
        ctx.session.execute(
            select(Sale.customer_id, func.sum(Sale.total_xof))
            .where(Sale.payment_mode == "credit")
            .group_by(Sale.customer_id)
        ).all()
    )
    paid = dict(
        ctx.session.execute(
            select(CreditPayment.customer_id, func.sum(CreditPayment.amount_xof)).group_by(
                CreditPayment.customer_id
            )
        ).all()
    )
    last_credit = dict(
        ctx.session.execute(
            select(Sale.customer_id, func.max(Sale.sold_at))
            .where(Sale.payment_mode == "credit")
            .group_by(Sale.customer_id)
        ).all()
    )
    last_payment = dict(
        ctx.session.execute(
            select(CreditPayment.customer_id, func.max(CreditPayment.paid_at)).group_by(
                CreditPayment.customer_id
            )
        ).all()
    )
    result = {}
    for cid, name in ctx.session.execute(select(Customer.id, Customer.name)):
        owed = int(credit.get(cid, 0)) - int(paid.get(cid, 0))
        result[cid] = {
            "client": name,
            "reste_a_payer_xof": owed,
            "dernier_achat_a_credit": _dt(last_credit[cid]) if cid in last_credit else None,
            "dernier_remboursement": _dt(last_payment[cid]) if cid in last_payment else None,
        }
    return result


class DebtsArgs(StrictModel):
    limite: int = Field(description="nombre de clients affichés, 1 à 20")


def debts(ctx: ToolContext, args: DebtsArgs) -> dict[str, Any]:
    limit = min(max(args.limite, 1), MAX_ROWS)
    owing = sorted(
        (b for b in _balances(ctx).values() if b["reste_a_payer_xof"] > 0),
        key=lambda b: b["reste_a_payer_xof"],
        reverse=True,
    )
    return {
        "total_du_xof": sum(b["reste_a_payer_xof"] for b in owing),
        "nombre_de_clients": len(owing),
        "clients": owing[:limit],
    }


class CustomerArgs(StrictModel):
    nom: str = Field(description="nom ou prénom du client")


def customer_overview(ctx: ToolContext, args: CustomerArgs) -> dict[str, Any]:
    name = _one("client", args.nom, _customer_names(ctx))
    customer = ctx.session.scalar(select(Customer).where(Customer.name == name))
    assert customer is not None and customer.id is not None
    balance = _balances(ctx)[customer.id]
    since = datetime.combine(ctx.today - timedelta(days=29), datetime.min.time())
    spent, visits = ctx.session.execute(
        select(func.coalesce(func.sum(Sale.total_xof), 0), func.count(Sale.id)).where(
            Sale.customer_id == customer.id, Sale.sold_at >= since
        )
    ).one()
    recent = ctx.session.execute(
        select(Sale.number, Sale.sold_at, Sale.payment_mode, Sale.total_xof)
        .where(Sale.customer_id == customer.id)
        .order_by(Sale.sold_at.desc())
        .limit(5)
    )
    return {
        **balance,
        "achats_30_derniers_jours_xof": int(spent),
        "passages_30_derniers_jours": int(visits),
        "dernieres_factures": [
            {
                "numero": n,
                "date": _dt(d),
                "paiement": PAYMENT_LABELS.get(m, m),
                "montant_xof": t,
            }
            for n, d, m, t in recent
        ],
    }


class NoArgs(StrictModel):
    pass


def low_stock(ctx: ToolContext, _: NoArgs) -> dict[str, Any]:
    since = datetime.combine(ctx.today - timedelta(days=13), datetime.min.time())
    sold = dict(
        ctx.session.execute(
            select(SaleLine.product_id, func.sum(SaleLine.quantity))
            .join(Sale, Sale.id == SaleLine.sale_id)
            .where(Sale.sold_at >= since)
            .group_by(SaleLine.product_id)
        ).all()
    )
    products = ctx.session.scalars(
        select(Product)
        .where(Product.stock <= Product.reorder_level)
        .order_by((Product.stock / Product.reorder_level).asc())
    )
    rows = []
    for p in products:
        daily = float(sold.get(p.id, 0)) / 14
        rows.append(
            {
                "produit": p.name,
                "unite": p.unit,
                "stock": _qty(p.stock),
                "seuil": _qty(p.reorder_level),
                "jours_restants": round(p.stock / daily, 1) if daily else None,
                "a_commander": _qty(max(p.reorder_level * 2 - p.stock, 0)),
            }
        )
    return {"produits": rows}


class ProductSalesArgs(PeriodArgs):
    produit: str = Field(description="nom du produit tel qu'il figure au catalogue")


def product_sales(ctx: ToolContext, args: ProductSalesArgs) -> dict[str, Any]:
    rng = ctx.period(args)
    name = _one("produit", args.produit, list(ctx.session.scalars(select(Product.name))))
    product = ctx.session.scalar(select(Product).where(Product.name == name))
    assert product is not None
    q, rev, n = ctx.session.execute(
        select(
            func.coalesce(func.sum(SaleLine.quantity), 0),
            func.coalesce(func.sum(SaleLine.line_total_xof), 0),
            func.count(func.distinct(SaleLine.sale_id)),
        )
        .join(Sale, Sale.id == SaleLine.sale_id)
        .where(SaleLine.product_id == product.id, _in(rng))
    ).one()
    days = max((rng.end - rng.start).days, 1)
    return {
        "periode": rng.as_dict(),
        "produit": product.name,
        "unite": product.unit,
        "prix_xof": product.price_xof,
        "quantite": _qty(float(q)),
        "chiffre_affaires_xof": int(rev),
        "nombre_de_ventes": int(n),
        "moyenne_par_jour": _qty(float(q) / days),
        "stock": _qty(product.stock),
    }


# --- Registry ---


@dataclass(frozen=True)
class Tool:
    name: str
    title: str  # French title of the card shown on screen
    description: str
    input_model: type[StrictModel]
    run: Callable[[ToolContext, Any], dict[str, Any]]


TOOLS: tuple[Tool, ...] = (
    Tool(
        "top_produits",
        "Produits",
        "Classement des produits sur une période : les plus (ou moins) vendus, par nombre "
        "de ventes, quantité, chiffre d'affaires ou marge.",
        TopProductsArgs,
        top_products,
    ),
    Tool(
        "chiffre_affaires",
        "Chiffre d'affaires",
        "Chiffre d'affaires, marge, nombre de factures et panier moyen d'une période, "
        "éventuellement détaillés par jour, semaine, mois, mode de paiement ou catégorie.",
        RevenueArgs,
        revenue,
    ),
    Tool(
        "lister_factures",
        "Factures",
        "Liste des factures (tickets de caisse) d'une période, filtrables par client et "
        "mode de paiement, avec leur nombre et leur montant total.",
        ListSalesArgs,
        list_sales,
    ),
    Tool(
        "detail_facture",
        "Facture",
        "Contenu détaillé d'une facture à partir de son numéro.",
        SaleDetailArgs,
        sale_detail,
    ),
    Tool(
        "dettes_clients",
        "Crédits clients",
        "Clients qui doivent de l'argent à la boutique (achats à crédit non remboursés), "
        "du plus gros montant au plus petit, avec le total dû.",
        DebtsArgs,
        debts,
    ),
    Tool(
        "situation_client",
        "Client",
        "Fiche d'un client : ce qu'il doit, ses achats des 30 derniers jours et ses "
        "dernières factures.",
        CustomerArgs,
        customer_overview,
    ),
    Tool(
        "stock_bas",
        "Stock à racheter",
        "Produits dont le stock est sous le seuil de réapprovisionnement, avec le nombre "
        "de jours restants et la quantité conseillée à commander.",
        NoArgs,
        low_stock,
    ),
    Tool(
        "ventes_produit",
        "Ventes d'un produit",
        "Ventes d'un produit précis sur une période : quantité, chiffre d'affaires, nombre "
        "de ventes, moyenne par jour et stock actuel.",
        ProductSalesArgs,
        product_sales,
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


# The final answer is itself a tool call, so its language is structured for the voice.
Language = Literal["fr", "wo", "en", "ff"]
ANSWER_TOOL = "repondre"


class AnswerArgs(StrictModel):
    texte: str = Field(description="réponse parlée, dans la langue de la question")
    langue: Language = Field(description="fr français, wo wolof, en anglais, ff pulaar")
