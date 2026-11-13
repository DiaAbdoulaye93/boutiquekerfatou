"""Score speech-to-text results against bench/references.json.

    uv run --no-project python bench/score.py bench/results/*.json

Each results file is {"engine": "...", "wo": {"01": "transcript", ...}, "fr": {...}}.
Reports the word error rate (WER) per language, plus whether the words the assistant
needs (customer names, numbers, products) were heard.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

BENCH = Path(__file__).resolve().parent
# Words the demo cannot do without: a miss here breaks the answer, not just the transcript.
KEY_WORDS = {
    "modou", "diop", "ndeye", "mbaye", "ceeb", "riz", "1243", "facture", "factures",
    "credit", "bor", "kilo", "kilos",
}
NUMBER_WORDS = {"mille deux cent quarante-trois": "1243", "mille deux cent quarante trois": "1243"}


def normalize(text: str) -> list[str]:
    text = text.casefold()
    for words, digits in NUMBER_WORDS.items():
        text = text.replace(words, digits)
    text = text.replace("1 243", "1243")
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    text = re.sub(r"[^\w\s]", " ", text.replace("-", " "))
    return text.split()


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1]


def main() -> None:
    refs = json.loads((BENCH / "references.json").read_text(encoding="utf-8"))
    for path in sys.argv[1:]:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
        print(f"\n=== {result['engine']}")
        for lang, expected in refs.items():
            if lang.startswith("_") or lang not in result:
                continue
            errors = words = keys_ok = keys = 0
            for n, ref_text in expected.items():
                hyp_text = result[lang].get(n, "")
                ref, hyp = normalize(ref_text), normalize(hyp_text)
                errors += edit_distance(ref, hyp)
                words += len(ref)
                wanted = [w for w in ref if w in KEY_WORDS]
                keys += len(wanted)
                keys_ok += sum(w in hyp for w in wanted)
                print(f"  {lang}/{n}  {hyp_text!r}")
            key_rate = f"{keys_ok}/{keys} mots clés" if keys else ""
            print(f"  -> {lang}: WER {100 * errors / max(words, 1):.0f} %  {key_rate}")


if __name__ == "__main__":
    main()
