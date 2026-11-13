"""Database tables of the fictional shop.

Amounts are whole FCFA (XOF has no subunit). Dates are naive local time: Senegal is on
UTC+0 all year, so local time and UTC coincide.
"""

from typing import Literal

from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

PaymentMode = Literal["especes", "mobile_money", "credit"]


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category: str
    unit: str  # "kg", "litre", "paquet", "sac de 50 kg"...
    price_xof: int  # selling price per unit
    cost_xof: int  # purchase price per unit
    stock: float
    reorder_level: float  # below this, the product must be bought again


class Customer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)


class Sale(SQLModel, table=True):
    """One receipt (« facture ») of the shop."""

    id: int | None = Field(default=None, primary_key=True)
    number: str = Field(index=True, unique=True)  # F-000123
    sold_at: NaiveDatetime = Field(index=True)
    customer_id: int | None = Field(default=None, foreign_key="customer.id", index=True)
    payment_mode: str  # PaymentMode
    total_xof: int


class SaleLine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sale_id: int = Field(foreign_key="sale.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    quantity: float
    unit_price_xof: int
    line_total_xof: int


class CreditPayment(SQLModel, table=True):
    """Money a customer brings back to pay off what they bought on credit."""

    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    paid_at: NaiveDatetime = Field(index=True)
    amount_xof: int
