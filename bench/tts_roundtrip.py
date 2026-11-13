"""Intelligibility check: transcribe each synthesized Wolof sample back with Scribe.

    uv run --no-project --with spekoai --with python-dotenv python bench/tts_roundtrip.py

A machine that understands the voice is no proof that a person will, but a voice the
transcriber cannot follow is almost always hard to follow by ear too.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from score import edit_distance, normalize
from spekoai import Speko
from speko_tts import SENTENCES, VARIANTS

BENCH = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(BENCH.parent / "backend" / ".env")
    key = os.environ.get("SPEKO_API_KEY") or sys.exit("SPEKO_API_KEY absente de backend/.env")
    speko = Speko(api_key=key, timeout=90)
    try:
        for variant in VARIANTS:
            errors = words = 0
            for sid, (lang, text) in SENTENCES.items():
                if lang != "wo":
                    continue
                path = BENCH / "tts" / f"{variant}-{sid}.wav"
                if not path.exists():
                    continue
                heard = speko.transcribe(path.read_bytes(), language="wo").text
                ref = normalize(text)
                errors += edit_distance(ref, normalize(heard))
                words += len(ref)
                print(f"  {variant}-{sid}: {heard}")
            if words:
                print(f"-> {variant}: {100 * errors / words:.0f} % d'erreurs à la réécoute")
    finally:
        speko.close()


if __name__ == "__main__":
    main()
