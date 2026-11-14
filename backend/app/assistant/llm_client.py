"""Single entry point for Claude API calls (adapted from the SAT verbatim analyzer).

No other module imports `anthropic`. Every call records its usage (tokens, model,
duration, step) in `client.usage`; tests inject a fake implementing `LlmClient`.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from app.config import Effort, ModelPricing, Settings

logger = logging.getLogger(__name__)

SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models served faster with `speed: "fast"` (no beta flag), at twice the token price.
FAST_MODE_MODELS = frozenset({"claude-opus-5-5"})


class LlmError(RuntimeError):
    """A Claude call failed for good. The message is shown to the user (French)."""


TRUNCATED_MESSAGE = "la réponse du modèle a dépassé la longueur maximale autorisée"
REFUSAL_MESSAGE = "le modèle a refusé de traiter cette demande"
CONNECTION_MESSAGE = "impossible de joindre le service Claude (problème de connexion)"


def _status_message(status_code: int) -> str:
    if status_code in (401, 403):
        return "la clé API Anthropic est invalide ou n'a pas les droits nécessaires"
    if status_code == 429:
        return "la limite de débit de l'API Claude est atteinte, réessayez dans un instant"
    if status_code >= 500:
        return "le service Claude est momentanément indisponible, réessayez plus tard"
    return f"le service Claude a renvoyé une erreur (code {status_code})"


@dataclass(frozen=True)
class LlmUsage:
    step: str
    model: str
    input_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    output_tokens: int
    duration_ms: int

    def cost_usd(self, pricing: dict[str, ModelPricing]) -> float | None:
        price = pricing.get(self.model)
        if price is None:
            return None
        return price.cost(
            self.input_tokens,
            self.cache_creation_tokens,
            self.cache_read_tokens,
            self.output_tokens,
        )


class LlmClient(Protocol):
    usage: list[LlmUsage]

    def converse(
        self,
        *,
        step: str,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        effort: Effort,
    ) -> Any:
        """One Messages API call; returns the response (content blocks + stop_reason)."""
        ...


class AnthropicLlmClient:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        if client is None:
            if settings.anthropic_api_key is None:
                raise LlmError("la clé ANTHROPIC_API_KEY n'est pas configurée")
            client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                max_retries=settings.llm_max_retries,
            )
        self._client = client
        self._settings = settings
        self.usage: list[LlmUsage] = []

    def converse(
        self,
        *,
        step: str,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        effort: Effort,
    ) -> Any:
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            # Tools and system prompt are stable across questions: cache them.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "tools": tools,
            # Forced tool_choice is rejected by the 5.5 models: the prompt steers instead.
            "tool_choice": {"type": "auto"},
            "output_config": {"effort": effort},
        }
        if self._settings.assistant_fast_mode and model in FAST_MODE_MODELS:
            params["speed"] = "fast"
        start = time.perf_counter()
        try:
            try:
                response = self._send(model, params)
            except anthropic.RateLimitError:
                # Fast mode has its own rate limit: fall back to standard speed once.
                if "speed" not in params:
                    raise
                logger.warning("%s: fast mode rate-limited, retrying at standard speed", step)
                params.pop("speed")
                response = self._send(model, params)
        except anthropic.APIStatusError as exc:
            logger.error("%s: API error %d: %s", step, exc.status_code, exc.message)
            raise LlmError(_status_message(exc.status_code)) from exc
        except anthropic.APIConnectionError as exc:
            logger.error("%s: connection error: %s", step, exc)
            raise LlmError(CONNECTION_MESSAGE) from exc
        duration_ms = round((time.perf_counter() - start) * 1000)
        self._record(step, response, duration_ms)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            logger.error("%s: refusal (category=%s)", step, getattr(details, "category", None))
            raise LlmError(REFUSAL_MESSAGE)
        if response.stop_reason == "max_tokens":
            logger.error("%s: response hit max_tokens=%d", step, max_tokens)
            raise LlmError(TRUNCATED_MESSAGE)
        return response

    def _send(self, model: str, params: dict[str, Any]) -> Any:
        if model in self._settings.server_fallback_models:
            return self._client.beta.messages.create(
                betas=[SERVER_FALLBACK_BETA], fallbacks="default", **params
            )
        return self._client.messages.create(**params)

    def _record(self, step: str, response: Any, duration_ms: int) -> None:
        usage = response.usage
        entry = LlmUsage(
            step=step,
            model=response.model,
            input_tokens=usage.input_tokens,
            cache_creation_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            output_tokens=usage.output_tokens,
            duration_ms=duration_ms,
        )
        self.usage.append(entry)
        logger.info(
            "%s: model=%s in=%d cache_write=%d cache_read=%d out=%d %dms",
            step,
            entry.model,
            entry.input_tokens,
            entry.cache_creation_tokens,
            entry.cache_read_tokens,
            entry.output_tokens,
            duration_ms,
        )
