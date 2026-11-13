"""Answer one question: Claude picks the business tools, reads their results, then calls
`repondre` with the spoken answer and its language.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from importlib.resources import files
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlmodel import Session

from app.assistant.llm_client import LlmClient, LlmError, LlmUsage
from app.assistant.periods import fr_date
from app.assistant.tools import (
    ANSWER_TOOL,
    TOOLS,
    TOOLS_BY_NAME,
    AnswerArgs,
    ToolContext,
    ToolInputError,
)
from app.config import Settings
from app.models import Customer, Product, Sale

logger = logging.getLogger(__name__)

TOO_MANY_STEPS = "l'assistant n'a pas réussi à conclure, reformulez la question"
_UNSUPPORTED_SCHEMA_KEYS = frozenset({"title", "default"})


@dataclass(frozen=True)
class Card:
    tool: str
    title: str
    data: dict[str, Any]


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    text: str


@dataclass
class AgentAnswer:
    text: str
    language: str
    cards: list[Card] = field(default_factory=list)
    usage: list[LlmUsage] = field(default_factory=list)
    duration_ms: int = 0


def _clean_schema(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key in _UNSUPPORTED_SCHEMA_KEYS:
            continue
        if key in ("properties", "$defs"):
            cleaned[key] = {name: _clean_schema(child) for name, child in value.items()}
        else:
            cleaned[key] = _clean_schema(value)
    if cleaned.get("type") == "object":
        cleaned["additionalProperties"] = False
        cleaned.setdefault("properties", {})
        cleaned["required"] = list(cleaned["properties"])
    return cleaned


def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema of a Pydantic model, in the shape strict tool use expects."""
    return _clean_schema(model.model_json_schema())


@cache
def tool_definitions() -> list[dict[str, Any]]:
    definitions = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": to_strict_schema(tool.input_model),
            "strict": True,
        }
        for tool in TOOLS
    ]
    definitions.append(
        {
            "name": ANSWER_TOOL,
            "description": "Donne la réponse finale, lue à voix haute. À appeler seul, en dernier.",
            "input_schema": to_strict_schema(AnswerArgs),
            "strict": True,
        }
    )
    return definitions


@cache
def _template() -> str:
    return (files("app.assistant") / "prompts" / "system.md").read_text(encoding="utf-8")


def system_prompt(session: Session, settings: Settings, today: date) -> str:
    """Stable for a whole day (date, catalogue, customers), so it stays in the cache."""
    products = session.scalars(select(Product).order_by(Product.category, Product.name)).all()
    catalog = "\n".join(
        f"- {p.name} — {p.unit} — {p.price_xof} FCFA ({p.category})" for p in products
    )
    customers = ", ".join(session.scalars(select(Customer.name).order_by(Customer.name)))
    first = session.scalar(select(func.min(Sale.sold_at)))
    return _template().format(
        shop_name=settings.shop_name,
        today=f"{fr_date(today)} ({today.isoformat()})",
        first_day=fr_date(first.date() if first else today),
        catalog=catalog,
        customers=customers,
    )


def _history(turns: list[Turn], keep: int) -> list[dict[str, Any]]:
    """Previous turns as plain text, alternating roles and starting with the user."""
    messages: list[dict[str, Any]] = []
    for turn in turns[-keep:]:
        text = turn.text.strip()
        if not text:
            continue
        if messages and messages[-1]["role"] == turn.role:
            messages[-1]["content"] += "\n" + text
        else:
            messages.append({"role": turn.role, "content": text})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if messages and messages[-1]["role"] == "user":
        messages.pop()  # the new question follows: never two user turns in a row
    return messages


def _result(block_id: str, content: str, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "tool_result", "tool_use_id": block_id, "content": content}
    if is_error:
        result["is_error"] = True
    return result


def answer(
    question: str,
    history: list[Turn],
    *,
    session: Session,
    client: LlmClient,
    settings: Settings,
    today: date,
) -> AgentAnswer:
    start = time.perf_counter()
    ctx = ToolContext(session=session, today=today)
    system = system_prompt(session, settings, today)
    messages = _history(history, settings.assistant_history_turns)
    messages.append({"role": "user", "content": question})
    cards: list[Card] = []

    def done(text: str, language: str) -> AgentAnswer:
        return AgentAnswer(
            text=text.strip(),
            language=language,
            cards=cards,
            usage=list(client.usage),
            duration_ms=round((time.perf_counter() - start) * 1000),
        )

    for step in range(1, settings.assistant_max_steps + 1):
        response = client.converse(
            step=f"ask:{step}",
            model=settings.assistant_model,
            system=system,
            messages=messages,
            tools=tool_definitions(),
            max_tokens=settings.assistant_max_tokens,
            effort=settings.assistant_effort,
        )
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            # The model answered in plain text instead of calling `repondre`: accept it.
            text = "".join(b.text for b in response.content if b.type == "text")
            if text.strip():
                return done(text, "fr")
            raise LlmError(TOO_MANY_STEPS)

        messages.append({"role": "assistant", "content": response.content})
        results: list[dict[str, Any]] = []
        final: AnswerArgs | None = None
        for call in calls:
            if call.name == ANSWER_TOOL:
                if len(calls) > 1:
                    results.append(
                        _result(call.id, "appeler repondre seul, après les résultats", True)
                    )
                    continue
                try:
                    final = AnswerArgs.model_validate(call.input)
                    results.append(_result(call.id, "ok"))
                except ValidationError as exc:
                    results.append(_result(call.id, f"arguments invalides : {exc}", True))
                continue

            tool = TOOLS_BY_NAME.get(call.name)
            if tool is None:
                results.append(_result(call.id, f"outil inconnu : {call.name}", True))
                continue
            try:
                args = tool.input_model.model_validate(call.input)
                data = tool.run(ctx, args)
            except ValidationError as exc:
                results.append(_result(call.id, f"arguments invalides : {exc}", True))
                continue
            except ToolInputError as exc:
                logger.info("%s: %s", call.name, exc)
                results.append(_result(call.id, str(exc), True))
                continue
            cards.append(Card(tool=tool.name, title=tool.title, data=data))
            results.append(_result(call.id, json.dumps(data, ensure_ascii=False)))

        if final is not None:
            return done(final.texte, final.langue)
        messages.append({"role": "user", "content": results})

    logger.error("no answer after %d steps", settings.assistant_max_steps)
    raise LlmError(TOO_MANY_STEPS)
