"""Transcribe the bench recordings through Speko (audio sent as bytes, no public URL).

Needs SPEKO_API_KEY in backend/.env (ignored by git).

    uv run --no-project --with spekoai --with python-dotenv python bench/speko_stt.py [provider]

Without a provider, Speko's router picks one per language. With one (elevenlabs,
gemini, openai...), only that provider is allowed. Writes bench/results/speko-<x>.json.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from spekoai import AllowedProviders, PipelineConstraints, Speko

BENCH = Path(__file__).resolve().parent
LANGS = ("wo", "fr", "en")
# Proper nouns and shop words the demo depends on; casing matters for names.
KEYWORDS = ["Modou Diop", "Ndèye Mbaye", "Keur Fatou", "ceeb", "bor", "facture"]


def main() -> None:
    load_dotenv(BENCH.parent / "backend" / ".env")
    key = os.environ.get("SPEKO_API_KEY")
    if not key:
        sys.exit("SPEKO_API_KEY absente de backend/.env")
    provider = sys.argv[1] if len(sys.argv) > 1 else None
    constraints = (
        PipelineConstraints(allowedProviders=AllowedProviders(stt=[provider])) if provider else None
    )
    name = provider or "auto"
    result: dict[str, object] = {"engine": f"Speko {name}"}
    speko = Speko(api_key=key, timeout=60)
    try:
        for lang in LANGS:
            transcripts, used = {}, set()
            for wav in sorted((BENCH / "wav" / lang).glob("*.wav")):
                try:
                    out = speko.transcribe(
                        wav.read_bytes(),
                        language=lang,
                        content_type="audio/wav",
                        constraints=constraints,
                        keywords=KEYWORDS,
                    )
                except Exception as exc:  # report and keep going: one refusal is a result too
                    print(f"{lang}/{wav.stem}: ERREUR {type(exc).__name__}: {str(exc)[:200]}")
                    transcripts[wav.stem] = ""
                    continue
                transcripts[wav.stem] = out.text.strip()
                used.add(f"{out.provider}/{out.model}")
                print(f"{lang}/{wav.stem} [{out.provider}/{out.model}]: {out.text.strip()}")
            result[lang] = transcripts
            result[f"{lang}_models"] = sorted(used)
    finally:
        speko.close()
    out_path = BENCH / "results" / f"speko-{name}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", out_path)


if __name__ == "__main__":
    main()
