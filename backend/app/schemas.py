"""Request and response bodies of the HTTP API (mirrored in frontend/src/app/core/models.ts)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[TurnIn] = Field(default_factory=list, max_length=20)


class CardOut(BaseModel):
    tool: str
    title: str
    data: dict[str, Any]


class AskOut(BaseModel):
    answer: str
    language: Literal["fr", "wo", "en", "ff"]
    cards: list[CardOut]
    model: str
    duration_ms: int
    llm_calls: int
    cost_usd: float | None


class TranscribeOut(BaseModel):
    text: str  # what was heard
    provider: str
    duration_ms: int


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    language: Literal["fr", "wo", "en", "ff"]


class ShopOut(BaseModel):
    name: str
    fictional: Literal[True] = True
    first_day: str | None
    last_day: str | None
    products: int
    customers: int
    receipts: int
