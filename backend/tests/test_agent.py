"""The tool loop around Claude, with a scripted fake client."""

import pytest
from sqlmodel import Session

from app.assistant.agent import Turn, _history, answer, tool_definitions
from app.assistant.llm_client import LlmError
from app.config import get_settings
from tests.conftest import TODAY
from tests.fakes import FakeLlmClient, reply, text, tool_use

DEBTS = tool_use("dettes_clients", {"limite": 3}, "c1")


def final(value: str, language: str = "fr", call_id: str = "c9") -> object:
    return reply(tool_use("repondre", {"texte": value, "langue": language}, call_id))


def ask(session: Session, client: FakeLlmClient, history: list[Turn] | None = None):
    return answer(
        "Qui me doit le plus ?",
        history or [],
        session=session,
        client=client,
        settings=get_settings(),
        today=TODAY,
    )


def test_tool_then_answer(session: Session) -> None:
    client = FakeLlmClient([reply(text("Je regarde."), DEBTS), final("Saliou te doit le plus.")])
    result = ask(session, client)
    assert result.text == "Saliou te doit le plus." and result.language == "fr"
    assert [c.tool for c in result.cards] == ["dettes_clients"]
    assert len(result.usage) == 2
    # The second request carries the tool result next to the assistant turn.
    second = client.requests[1]["messages"]
    assert second[-1]["content"][0]["tool_use_id"] == "c1"
    assert "total_du_xof" in second[-1]["content"][0]["content"]


def test_bad_arguments_go_back_to_the_model(session: Session) -> None:
    bad = tool_use("situation_client", {"nom": "Zorro"}, "c1")
    client = FakeLlmClient([reply(bad), final("Je ne connais pas ce client.")])
    result = ask(session, client)
    error = client.requests[1]["messages"][-1]["content"][0]
    assert error["is_error"] is True and "aucun client" in error["content"]
    assert result.cards == []


def test_answer_with_other_tools_is_refused(session: Session) -> None:
    rushed = reply(DEBTS, tool_use("repondre", {"texte": "trop tôt", "langue": "fr"}, "c2"))
    client = FakeLlmClient([rushed, final("Voilà.", "wo")])
    result = ask(session, client)
    assert result.text == "Voilà." and result.language == "wo"
    results = client.requests[1]["messages"][-1]["content"]
    assert results[1]["is_error"] is True


def test_plain_text_answer_is_accepted(session: Session) -> None:
    result = ask(session, FakeLlmClient([reply(text("Bonjour !"))]))
    assert result.text == "Bonjour !" and result.language == "fr"


def test_gives_up_after_max_steps(session: Session) -> None:
    steps = get_settings().assistant_max_steps
    client = FakeLlmClient([reply(DEBTS) for _ in range(steps)])
    with pytest.raises(LlmError):
        ask(session, client)


def test_history_alternates_and_ends_with_assistant() -> None:
    turns = [
        Turn("assistant", "orphelin"),
        Turn("user", "a"),
        Turn("user", "b"),
        Turn("assistant", "c"),
        Turn("user", "sans réponse"),
    ]
    assert _history(turns, keep=10) == [
        {"role": "user", "content": "a\nb"},
        {"role": "assistant", "content": "c"},
    ]


def test_tool_schemas_are_strict() -> None:
    for tool in tool_definitions():
        schema = tool["input_schema"]
        assert tool["strict"] is True and schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
