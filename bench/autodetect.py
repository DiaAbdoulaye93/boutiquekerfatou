"""Can Scribe transcribe without being told the language? Every recording is sent with
the same settings, whatever language was spoken.

    uv run --no-project --with spekoai --with python-dotenv python bench/autodetect.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from score import edit_distance, normalize
from spekoai import AllowedProviders, PipelineConstraints, Speko

BENCH = Path(__file__).resolve().parent
ONLY_SCRIBE = PipelineConstraints(allowedProviders=AllowedProviders(stt=["elevenlabs"]))
# (routing language, provider-facing language): how each strategy calls Speko.
STRATEGIES = {
    "wo-for-all": ("wo", None),
    "fr-for-all": ("fr", None),
    "auto": ("wo", "auto"),
}


def main() -> None:
    load_dotenv(BENCH.parent / "backend" / ".env")
    key = os.environ.get("SPEKO_API_KEY") or sys.exit("SPEKO_API_KEY absente")
    refs = json.loads((BENCH / "references.json").read_text(encoding="utf-8"))
    speko = Speko(api_key=key, timeout=60)
    for name, (routing, stt_language) in STRATEGIES.items():
        print(f"=== {name}")
        for lang in ("wo", "fr", "en"):
            errors = words = 0
            for wav in sorted((BENCH / "wav" / lang).glob("*.wav")):
                try:
                    out = speko.transcribe(
                        wav.read_bytes(),
                        language=routing,
                        stt_language=stt_language,
                        content_type="audio/wav",
                        constraints=ONLY_SCRIBE,
                    )
                    text = out.text.strip()
                except Exception as exc:
                    print(f"  {lang}/{wav.stem}: ERREUR {str(exc)[:120]}")
                    text = ""
                ref = normalize(refs[lang][wav.stem])
                errors += edit_distance(ref, normalize(text))
                words += len(ref)
                print(f"  {lang}/{wav.stem}: {text}")
            print(f"  -> {lang}: {100 * errors / words:.0f} % d'erreurs")
    speko.close()


if __name__ == "__main__":
    main()
