"""Spoken questions: /api/transcribe then /api/ask then /api/speak (Speko faked)."""

import wave
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import get_settings
from app.main import create_app
from app.voice.client import VoiceError, playable
from tests.fakes import FakeVoiceClient, factory

AUDIO = {"audio": ("q.webm", b"\x1a\x45\xdf\xa3 fake opus", "audio/webm;codecs=opus")}


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "slide_dates_on_startup", False)
    monkeypatch.setattr(get_settings(), "app_password", None)


@pytest.fixture
def voice() -> FakeVoiceClient:
    return FakeVoiceClient()


def make(shop_db: Engine, tmp_path: Path, voice_factory) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(
        create_app(shop_db, factory([]), static_dir=tmp_path, voice_client_factory=voice_factory)
    )


@pytest.fixture
def client(shop_db: Engine, tmp_path: Path, voice: FakeVoiceClient) -> Iterator[TestClient]:
    with make(shop_db, tmp_path, lambda _: voice) as client:
        yield client


def test_transcribe(client: TestClient, voice: FakeVoiceClient) -> None:
    body = client.post("/api/transcribe", files=AUDIO, data={"language": "wo"}).json()
    assert body == {"text": voice.heard, "provider": "fake", "duration_ms": 300}
    # The codecs parameter is dropped: providers want the container type.
    assert voice.calls == [("transcribe", "audio/webm", "wo")]


def test_language_is_optional(client: TestClient, voice: FakeVoiceClient) -> None:
    assert client.post("/api/transcribe", files=AUDIO).status_code == 200
    assert voice.calls == [("transcribe", "audio/webm", "auto")]


def test_speak_returns_playable_audio(client: TestClient, voice: FakeVoiceClient) -> None:
    response = client.post("/api/speak", json={"text": "Waaw.", "language": "wo"})
    assert response.status_code == 200 and response.content == b"RIFF....WAVE"
    assert response.headers["content-type"] == "audio/wav"
    assert voice.calls == [("synthesize", "Waaw.", "wo")]


def test_voice_failures_are_502(client: TestClient, voice: FakeVoiceClient) -> None:
    voice.fail_transcribe = voice.fail_synthesize = True
    response = client.post("/api/transcribe", files=AUDIO, data={"language": "fr"})
    assert response.status_code == 502 and "transcription" in response.json()["detail"]
    assert client.post("/api/speak", json={"text": "a", "language": "fr"}).status_code == 502


def test_missing_speko_key_is_a_503(shop_db: Engine, tmp_path: Path) -> None:
    def no_key(_: object) -> FakeVoiceClient:
        raise VoiceError("la clé SPEKO_API_KEY n'est pas configurée")

    with make(shop_db, tmp_path, no_key) as client:
        response = client.post("/api/transcribe", files=AUDIO, data={"language": "fr"})
    assert response.status_code == 503 and "SPEKO_API_KEY" in response.json()["detail"]


def test_silence_is_reported(client: TestClient, voice: FakeVoiceClient) -> None:
    voice.heard = ""
    response = client.post("/api/transcribe", files=AUDIO, data={"language": "fr"})
    assert response.status_code == 422 and "rien entendu" in response.json()["detail"]


def test_bad_inputs(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.post("/api/transcribe", files=AUDIO, data={"language": "de"}).status_code == 422
    assert client.post("/api/speak", json={"text": "", "language": "fr"}).status_code == 422
    monkeypatch.setattr(get_settings(), "max_audio_bytes", 4)
    response = client.post("/api/transcribe", files=AUDIO, data={"language": "fr"})
    assert response.status_code == 413


def test_raw_pcm_becomes_wav() -> None:
    pcm = b"\x00\x01" * 2400
    audio, content_type = playable(pcm, "audio/pcm;rate=24000")
    assert content_type == "audio/wav"
    with wave.open(BytesIO(audio)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 2400
    assert playable(b"mp3", "audio/mpeg") == (b"mp3", "audio/mpeg")
