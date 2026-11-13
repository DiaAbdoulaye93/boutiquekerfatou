"""Scripted stand-in for the Claude client: no network call in tests."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from app.assistant.llm_client import LlmError, LlmUsage
from app.config import Settings


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


def factory(script: list[Step]) -> Callable[[Settings], FakeLlmClient]:
    def make(_: Settings) -> FakeLlmClient:
        return FakeLlmClient(script)

    return make
