"""Speech to text and text to speech through Speko (single entry point, like llm_client).

Choices come from the voice bench (bench/, 13/11/2026), see the settings:
- listening: ElevenLabs Scribe in every language, pinned (the router sent French to
  slower or weaker engines);
- speaking: Gemini TTS for every language. No TTS provider accepts the "wo" code, so
  Wolof text is sent under the "fr" carrier code and the model reads it as written.
"""

import io
import logging
import time
import wave
from dataclasses import dataclass
from typing import Literal, Protocol

from spekoai import AllowedProviders, PipelineConstraints, Speko

from app.config import Settings

logger = logging.getLogger(__name__)

SpokenLanguage = Literal["fr", "wo", "en"]
# Proper nouns and shop words; casing matters for names.
KEYWORDS = ["Modou Diop", "Ndèye Mbaye", "Saliou Wade", "Keur Fatou", "ceeb", "bor", "facture"]
TTS_CARRIER = {"fr": "fr", "wo": "fr", "en": "en", "ff": "fr"}


class VoiceError(RuntimeError):
    """A speech call failed for good. The message is shown to the user (French)."""


@dataclass(frozen=True)
class Speech:
    audio: bytes
    content_type: str
    duration_ms: int


@dataclass(frozen=True)
class Transcript:
    text: str
    provider: str
    duration_ms: int


class VoiceClient(Protocol):
    def transcribe(
        self, audio: bytes, content_type: str, language: SpokenLanguage
    ) -> Transcript: ...

    def synthesize(self, text: str, language: str) -> Speech: ...


def _only(providers: list[str]) -> PipelineConstraints | None:
    return (
        PipelineConstraints(allowedProviders=AllowedProviders(stt=providers)) if providers else None
    )


class SpekoVoiceClient:
    def __init__(self, settings: Settings) -> None:
        if settings.speko_api_key is None:
            raise VoiceError("la clé SPEKO_API_KEY n'est pas configurée")
        self._speko = Speko(api_key=settings.speko_api_key.get_secret_value(), timeout=60)
        self._settings = settings

    def transcribe(self, audio: bytes, content_type: str, language: SpokenLanguage) -> Transcript:
        providers = self._settings.stt_providers.get(language, [])
        start = time.perf_counter()
        try:
            result = self._speko.transcribe(
                audio,
                language=language,
                content_type=content_type,
                constraints=_only(providers),
                keywords=KEYWORDS,
            )
        except Exception as exc:  # SDK and network errors alike: the user sees one message
            logger.error("transcribe(%s): %s: %s", language, type(exc).__name__, exc)
            raise VoiceError("la transcription du vocal a échoué, réessayez") from exc
        ms = round((time.perf_counter() - start) * 1000)
        logger.info(
            "transcribe(%s): %s/%s %dms failovers=%d",
            language,
            result.provider,
            result.model,
            ms,
            result.failover_count,
        )
        return Transcript(text=result.text.strip(), provider=result.provider, duration_ms=ms)

    def synthesize(self, text: str, language: str) -> Speech:
        start = time.perf_counter()
        constraints = PipelineConstraints(
            allowedProviders=AllowedProviders(tts=[self._settings.tts_provider])
        )
        try:
            result = self._speko.synthesize(
                text,
                language=TTS_CARRIER.get(language, "fr"),
                model=self._settings.tts_model,
                constraints=constraints,
            )
        except Exception as exc:
            logger.error("synthesize(%s): %s: %s", language, type(exc).__name__, exc)
            raise VoiceError("la synthèse vocale a échoué") from exc
        ms = round((time.perf_counter() - start) * 1000)
        logger.info("synthesize(%s): %s/%s %dms", language, result.provider, result.model, ms)
        audio, content_type = playable(result.audio, result.content_type)
        return Speech(audio=audio, content_type=content_type, duration_ms=ms)


def playable(audio: bytes, content_type: str) -> tuple[bytes, str]:
    """Browsers cannot play raw PCM: wrap it in a WAV header. Other formats pass as is."""
    base, *params = [part.strip() for part in content_type.split(";")]
    if base not in ("audio/pcm", "audio/l16", "audio/raw"):
        return audio, content_type
    rate = 24000
    for param in params:
        if param.startswith("rate="):
            rate = int(param.removeprefix("rate="))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)  # 16-bit little-endian, what the providers stream
        out.setframerate(rate)
        out.writeframes(audio)
    return buffer.getvalue(), "audio/wav"
