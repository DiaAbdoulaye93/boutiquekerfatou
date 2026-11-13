"""Questions to the assistant (typed or spoken), and the shop summary of the header."""

from collections.abc import Callable, Iterator
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlmodel import Session

from app.assistant.agent import Turn, answer
from app.assistant.llm_client import LlmClient, LlmError
from app.config import PRICING, Settings, get_settings
from app.models import Customer, Product, Sale
from app.schemas import AskIn, AskOut, CardOut, ShopOut, SpeakIn, TranscribeOut, TurnIn
from app.voice.client import SpokenLanguage, VoiceClient, VoiceError

router = APIRouter(prefix="/api", tags=["assistant"])

LlmClientFactory = Callable[[Settings], LlmClient]
VoiceClientFactory = Callable[[Settings], VoiceClient]
NOTHING_HEARD = "Je n'ai rien entendu. Rapprochez le téléphone et réessayez."


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_today() -> date:
    # Senegal is on UTC+0 all year: the server's UTC date is the shop's date.
    return date.today()


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TodayDep = Annotated[date, Depends(get_today)]


def _ask(
    question: str,
    history: list[TurnIn],
    request: Request,
    session: Session,
    settings: Settings,
    today: date,
) -> AskOut:
    factory: LlmClientFactory = request.app.state.llm_client_factory
    try:
        result = answer(
            question,
            [Turn(role=t.role, text=t.text) for t in history],
            session=session,
            client=factory(settings),
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


@router.post("/ask", response_model=AskOut)
def ask(
    body: AskIn, request: Request, session: SessionDep, settings: SettingsDep, today: TodayDep
) -> AskOut:
    return _ask(body.question, body.history, request, session, settings, today)


# A spoken question takes three calls, so the screen moves at each step: the words heard
# appear after about 2 s, the written answer and its cards next, the voice last.


def _voice_client(request: Request, settings: Settings) -> VoiceClient:
    factory: VoiceClientFactory = request.app.state.voice_client_factory
    try:
        return factory(settings)
    except VoiceError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.post("/transcribe", response_model=TranscribeOut)
def transcribe(
    request: Request,
    settings: SettingsDep,
    audio: Annotated[UploadFile, File(description="recorded question (webm, ogg, mp4, wav)")],
    language: Annotated[
        SpokenLanguage | None,
        Form(description="language spoken, if known; omitted, it is detected"),
    ] = None,
) -> TranscribeOut:
    data = audio.file.read(settings.max_audio_bytes + 1)
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "le vocal est trop long")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOTHING_HEARD)
    # "audio/webm;codecs=opus" -> "audio/webm": providers want the container type.
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()

    try:
        heard = _voice_client(request, settings).transcribe(data, content_type, language)
    except VoiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not heard.text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOTHING_HEARD)
    return TranscribeOut(text=heard.text, provider=heard.provider, duration_ms=heard.duration_ms)


@router.post(
    "/speak",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}, "audio/mpeg": {}}}},
)
def speak(body: SpeakIn, request: Request, settings: SettingsDep) -> Response:
    """The answer read aloud, as an audio file the browser plays directly."""
    try:
        speech = _voice_client(request, settings).synthesize(body.text, body.language)
    except VoiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return Response(
        speech.audio,
        media_type=speech.content_type,
        headers={"Cache-Control": "no-store", "X-Duration-Ms": str(speech.duration_ms)},
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
