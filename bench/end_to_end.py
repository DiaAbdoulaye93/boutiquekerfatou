"""Feed transcripts to the real assistant and check it calls the right tool.

    cd backend && uv run python ../bench/end_to_end.py ../bench/results/speko-auto.json wo fr

Uses backend/.env (Anthropic key, local database). Costs a few cents per question.
"""

import json
import sys
from datetime import date
from pathlib import Path

from sqlmodel import Session

from app.assistant.agent import answer
from app.assistant.llm_client import AnthropicLlmClient, LlmError
from app.config import PRICING, get_settings
from app.db import get_engine

# Tool that must be called for each question (same numbering in every language).
EXPECTED = {
    "wo": {
        "01": {"situation_client"},
        "02": {"dettes_clients"},
        "03": {"top_produits"},
        "04": {"chiffre_affaires"},
        "05": {"lister_factures"},
        "06": {"stock_bas"},
        "07": {"ventes_produit"},
        "08": {"detail_facture"},
        "09": {"situation_client", "lister_factures"},
        "10": {"chiffre_affaires"},
    },
    "fr": {
        "01": {"situation_client"},
        "02": {"top_produits"},
        "03": {"lister_factures"},
        "04": {"detail_facture"},
        "05": {"ventes_produit"},
    },
    "en": {"01": {"dettes_clients"}, "02": {"stock_bas"}, "03": {"situation_client", "lister_factures"}},
}


def main() -> None:
    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    langs = sys.argv[2:] or ["wo"]
    settings = get_settings()
    total_cost = 0.0
    ok = n = 0
    durations: list[int] = []
    with Session(get_engine()) as session:
        for lang in langs:
            for num, question in results[lang].items():
                expected = EXPECTED[lang][num]
                client = AnthropicLlmClient(settings)
                try:
                    r = answer(
                        question, [], session=session, client=client, settings=settings,
                        today=date.today(),
                    )
                except LlmError as exc:
                    print(f"{lang}/{num} ERREUR {exc}")
                    n += 1
                    continue
                tools = {c.tool for c in r.cards}
                good = bool(tools & expected)
                ok += good
                n += 1
                total_cost += sum(u.cost_usd(PRICING) or 0 for u in r.usage)
                mark = "OK " if good else "RATÉ"
                print(f"{mark} {lang}/{num} « {question} »")
                print(f"     outils={sorted(tools)} [{r.language}] {r.duration_ms} ms {r.text}")
                durations.append(r.duration_ms)
    median = sorted(durations)[len(durations) // 2] if durations else 0
    print(f"\n{ok}/{n} bons outils, médiane {median / 1000:.1f} s, coût {total_cost:.3f} $")


if __name__ == "__main__":
    main()
