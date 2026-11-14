"""Application settings, model names and pricing table."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    anthropic_api_key: SecretStr | None = None
    llm_max_retries: int = 3

    # Model answering the shopkeeper's questions. Latency matters for a voice demo:
    # try claude-haiku-5-5 here if the answers feel slow.
    assistant_model: str = "claude-opus-5-5"
    assistant_effort: Effort = "low"
    assistant_max_tokens: int = 8000
    # Opus 5.5 fast mode: up to 2.5x faster output, 2x the token price (8/40 $ per M).
    assistant_fast_mode: bool = True
    # Upper bound on model <-> tools round trips for one question.
    assistant_max_steps: int = 6
    # Previous turns sent back for follow-up questions ("et le mois dernier ?").
    assistant_history_turns: int = 6

    # Models sent with server-side refusal fallback (`fallbacks: "default"`).
    server_fallback_models: frozenset[str] = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})

    # Voice through Speko (bench/ results, 13/11/2026). Listening: ElevenLabs Scribe in
    # every language (Wolof 10/11 key words, French 3 % word errors, about 2 s).
    # Speaking: Gemini TTS; Flash-Lite answers in 1.5 s against 2 to 5 s for Flash.
    speko_api_key: SecretStr | None = None
    stt_providers: dict[str, list[str]] = {
        "wo": ["elevenlabs"],
        "fr": ["elevenlabs"],
        "en": ["elevenlabs"],
    }
    # No language chosen in the app: route as this language (Scribe) and send this
    # provider-facing language, which asks Scribe to detect the spoken language.
    auto_routing_language: str = "wo"
    auto_stt_language: str | None = "auto"
    tts_provider: str = "google"  # Speko's name for Gemini TTS
    tts_model: str | None = "gemini-3.8-flash-lite-tts"
    max_audio_bytes: int = 5_000_000  # about 5 minutes of Opus: far above one question

    database_url: str = "postgresql+psycopg://postgres@localhost:5432/boutique_vocale"
    test_database_url: str = "postgresql+psycopg://postgres@localhost:5432/boutique_vocale_test"

    # Fill an empty database with the fictional shop at startup (first deploy on Render).
    seed_on_startup: bool = True
    # Shift the fictional sales so that the last one is today: the demo never looks stale.
    slide_dates_on_startup: bool = True

    shop_name: str = "Boutique Keur Fatou"

    # HTTP Basic auth on the whole app (except /health) when a password is set: a public
    # demo URL must not let anyone spend the Anthropic budget.
    app_username: str = "boutique"
    app_password: SecretStr | None = None

    # Built Angular app (dist/.../browser) served by FastAPI; absent in development.
    static_dir: Path = BACKEND_DIR / "static"

    log_level: str = "INFO"

    @field_validator("anthropic_api_key", "app_password", "speko_api_key", mode="before")
    @classmethod
    def empty_is_unset(cls, value: object) -> object:
        """`APP_PASSWORD=` (empty, as in .env.example) means no password, not an empty one."""
        return None if value == "" else value

    @field_validator("database_url", "test_database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Accept the plain URLs given by hosted databases (Railway, Neon: postgresql://)."""
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


@dataclass(frozen=True)
class ModelPricing:
    """USD per million tokens."""

    input: float
    cache_write_5m: float
    cache_read: float
    output: float

    def cost(
        self, input_tokens: int, cache_write_tokens: int, cache_read_tokens: int, output_tokens: int
    ) -> float:
        """USD cost of one call."""
        return (
            input_tokens * self.input
            + cache_write_tokens * self.cache_write_5m
            + cache_read_tokens * self.cache_read
            + output_tokens * self.output
        ) / 1_000_000


# Source: Anthropic pricing page, checked 2026-11-13 (cache write = 1.25 x input).
# Haiku 5.5 rates are for prompts up to 100,000 tokens; our prompts stay far below that.
PRICING: dict[str, ModelPricing] = {
    "claude-opus-5-5": ModelPricing(input=4.00, cache_write_5m=5.00, cache_read=0.20, output=20.00),
    "claude-sonnet-5-5": ModelPricing(
        input=2.00, cache_write_5m=2.50, cache_read=0.10, output=10.00
    ),
    "claude-haiku-5-5": ModelPricing(
        input=0.10, cache_write_5m=0.125, cache_read=0.01, output=0.50
    ),
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
