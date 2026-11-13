"""Scripted stand-in for the Claude client: no network call in tests."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from app.assistant.llm_client import LlmError, LlmUsage
from app.config import Settings
from app.voice.client import Speech, Transcript, VoiceError


def tool_use(name: str, args: dict[str, Any], call_id: str = "call_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def reply(*blocks: SimpleNamespace) -> SimpleNamespace:
    stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


Step = SimpleNamespace | LlmError


class FakeLlmClient:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, script: list[Step], model: str = "claude-opus-5-5") -> None:
        self.script = list(script)
        self.model = model
        self.usage: list[LlmUsage] = []
        self.requests: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> Any:
        # Copy the messages: the agent keeps appending to the same list.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        step = self.script.pop(0)
        if isinstance(step, LlmError):
            raise step
        self.usage.append(LlmUsage(kwargs["step"], self.model, 1000, 0, 800, 120, 900))
        return step


class FakeVoiceClient:
    """Hears `heard`, speaks a short WAV; either step can be set to fail."""

    def __init__(self, heard: str = "Kan moo am bor bu gëna rëy ci man ?") -> None:
        self.heard = heard
        self.fail_transcribe = False
        self.fail_synthesize = False
        self.calls: list[tuple[str, ...]] = []

    def transcribe(self, audio: bytes, content_type: str, language: str) -> Transcript:
        self.calls.append(("transcribe", content_type, language))
        if self.fail_transcribe:
            raise VoiceError("la transcription du vocal a échoué, réessayez")
        return Transcript(text=self.heard, provider="fake", duration_ms=300)

    def synthesize(self, text: str, language: str) -> Speech:
        self.calls.append(("synthesize", text, language))
        if self.fail_synthesize:
            raise VoiceError("la synthèse vocale a échoué")
        return Speech(audio=b"RIFF....WAVE", content_type="audio/wav", duration_ms=500)


def factory(script: list[Step]) -> Callable[[Settings], FakeLlmClient]:
    def make(_: Settings) -> FakeLlmClient:
        return FakeLlmClient(script)

    return make
