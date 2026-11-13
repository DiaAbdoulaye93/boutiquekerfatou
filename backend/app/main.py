"""FastAPI application: REST API under /api, health check at /health, PWA at /."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Engine

from app.api.ask import LlmClientFactory, VoiceClientFactory
from app.api.ask import router as ask_router
from app.assistant.llm_client import AnthropicLlmClient
from app.auth import add_basic_auth
from app.config import get_settings
from app.db import get_engine, init_db
from app.schemas import HealthOut
from app.seed.generate import is_empty, seed_database, slide_to_today
from app.spa import INDEX, mount_spa
from app.voice.client import SpekoVoiceClient

APP_VERSION = version("boutique-vocale")
logger = logging.getLogger(__name__)


def create_app(
    engine: Engine | None = None,
    llm_client_factory: LlmClientFactory | None = None,
    static_dir: Path | None = None,
    voice_client_factory: VoiceClientFactory | None = None,
) -> FastAPI:
    """Build the app; tests pass their own engine, fake Claude and voice clients and a
    static folder."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = app.state.engine
        init_db(db)
        if settings.seed_on_startup and is_empty(db):
            logger.info("empty database: generating the fictional shop")
            seed_database(db)
        if settings.slide_dates_on_startup:
            slide_to_today(db)
        yield

    app = FastAPI(title="Boutique vocale", version=APP_VERSION, lifespan=lifespan)
    app.state.engine = engine or get_engine()
    app.state.llm_client_factory = llm_client_factory or AnthropicLlmClient
    app.state.voice_client_factory = voice_client_factory or SpekoVoiceClient
    app.include_router(ask_router)
    if settings.app_password is not None:
        add_basic_auth(app, settings.app_username, settings.app_password.get_secret_value())

    @app.exception_handler(RequestValidationError)
    async def log_validation_error(request: Request, exc: RequestValidationError) -> Response:
        # A 422 from the PWA means the app and the API disagree: log which field.
        fields = [
            f"{'.'.join(str(p) for p in error.get('loc', ()))}: {error.get('msg')}"
            for error in exc.errors()
        ]
        logger.warning("422 on %s %s: %s", request.method, request.url.path, "; ".join(fields))
        return await request_validation_exception_handler(request, exc)

    @app.get("/health", response_model=HealthOut, tags=["health"])
    def health() -> HealthOut:
        return HealthOut(version=APP_VERSION)

    # Registered last: its catch-all route must not shadow the API routes.
    spa_dir = static_dir or settings.static_dir
    if (spa_dir / INDEX).is_file():
        mount_spa(app, spa_dir)
    return app


app = create_app()
