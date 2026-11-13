"""Latency of candidate TTS and French STT engines through Speko (two runs each).

    uv run --no-project --with spekoai --with python-dotenv python bench/latency.py
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from spekoai import AllowedProviders, PipelineConstraints, Speko

BENCH = Path(__file__).resolve().parent
TEXT = "Modou Diop dafa la ameel 1 550 FCFA rekk."
TTS = [
    ("gemini-flash", "google", None),
    ("gemini-flash-lite", "google", "gemini-3.8-flash-lite-tts"),
    ("eleven-flash-v2.5", "elevenlabs", "eleven_flash_v2_5"),
    ("eleven-v4-turbo", "elevenlabs", "eleven_v4_turbo"),
]
STT = ["elevenlabs", "gemini", "google", "assemblyai"]


def main() -> None:
    load_dotenv(BENCH.parent / "backend" / ".env")
    key = os.environ.get("SPEKO_API_KEY") or sys.exit("SPEKO_API_KEY absente")
    speko = Speko(api_key=key, timeout=90)
    print("--- voix (même phrase wolof, 2 essais)")
    for label, provider, model in TTS:
        times, used = [], ""
        for _ in range(2):
            start = time.perf_counter()
            try:
                r = speko.synthesize(
                    TEXT,
                    language="fr",
                    model=model,
                    constraints=PipelineConstraints(
                        allowedProviders=AllowedProviders(tts=[provider])
                    ),
                )
            except Exception as exc:
                print(f"{label}: ERREUR {str(exc)[:150]}")
                break
            times.append(time.perf_counter() - start)
            used = f"{r.provider}/{r.model}"
            ext = "mp3" if "mpeg" in r.content_type else "wav"
            if "pcm" in r.content_type:
                from app_playable import playable  # noqa: PLC0415 - optional helper below

                data, _ = playable(r.audio, r.content_type)
            else:
                data = r.audio
            (BENCH / "tts" / f"speed-{label}.{ext}").write_bytes(data)
        if times:
            print(f"{label:18s} {used:40s} " + " / ".join(f"{t:.1f} s" for t in times))
    print("--- transcription en français")
    audio = sorted((BENCH / "wav" / "fr").glob("*.wav"))[1].read_bytes()
    for provider in STT:
        start = time.perf_counter()
        try:
            r = speko.transcribe(
                audio,
                language="fr",
                content_type="audio/wav",
                constraints=PipelineConstraints(allowedProviders=AllowedProviders(stt=[provider])),
            )
        except Exception as exc:
            print(f"{provider}: ERREUR {str(exc)[:150]}")
            continue
        took = time.perf_counter() - start
        print(f"{provider:12s} {r.provider}/{r.model:28s} {took:.1f} s :: {r.text}")
    speko.close()


if __name__ == "__main__":
    main()
