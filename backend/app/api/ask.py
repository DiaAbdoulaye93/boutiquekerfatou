"""Questions to the assistant, and the shop summary shown in the header."""

from collections.abc import Callable, Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlmodel import Session

from app.assistant.agent import Turn, answer
from app.assistant.llm_client import LlmClient, LlmError
from app.config import PRICING, Settings, get_settings
from app.models import Customer, Product, Sale
from app.schemas import AskIn, AskOut, CardOut, ShopOut

router = APIRouter(prefix="/api", tags=["assistant"])

LlmClientFactory = Callable[[Settings], LlmClient]


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_today() -> date:
    # Senegal is on UTC+0 all year: the server's UTC date is the shop's date.
    return date.today()


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TodayDep = Annotated[date, Depends(get_today)]


@router.post("/ask", response_model=AskOut)
def ask(
    body: AskIn, request: Request, session: SessionDep, settings: SettingsDep, today: TodayDep
) -> AskOut:
    factory: LlmClientFactory = request.app.state.llm_client_factory
    try:
        client = factory(settings)
        result = answer(
            body.question,
            [Turn(role=t.role, text=t.text) for t in body.history],
            session=session,
            client=client,
            settings=settings,
            today=today,
        )
    except LlmError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    costs = [u.cost_usd(PRICING) for u in result.usage]
    return AskOut(
        answer=result.text,
        language=result.language,  # type: ignore[arg-type]
        cards=[CardOut(tool=c.tool, title=c.title, data=c.data) for c in result.cards],
        model=result.usage[-1].model if result.usage else settings.assistant_model,
        duration_ms=result.duration_ms,
        llm_calls=len(result.usage),
        cost_usd=None if None in costs else round(sum(c for c in costs if c), 5),
    )


@router.get("/shop", response_model=ShopOut)
def shop(session: SessionDep, settings: SettingsDep) -> ShopOut:
    first, last, receipts = session.execute(
        select(func.min(Sale.sold_at), func.max(Sale.sold_at), func.count(Sale.id))
    ).one()
    return ShopOut(
        name=settings.shop_name,
        first_day=first.date().isoformat() if first else None,
        last_day=last.date().isoformat() if last else None,
        products=session.scalar(select(func.count()).select_from(Product)) or 0,
        customers=session.scalar(select(func.count()).select_from(Customer)) or 0,
        receipts=receipts,
    )
