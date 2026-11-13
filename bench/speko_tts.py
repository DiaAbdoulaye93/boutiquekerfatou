"""Speak sample Wolof answers with several TTS engines through Speko, to judge by ear.

    uv run --no-project --with spekoai --with python-dotenv python bench/speko_tts.py

Writes bench/tts/<variant>-<n>.<ext> and bench/tts/index.txt.
"""

import os
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv
from spekoai import AllowedProviders, PipelineConstraints, Speko

BENCH = Path(__file__).resolve().parent
OUT = BENCH / "tts"
CLONE = "JOM6qix7fsdKrpgiZzTX"  # the author's cloned voice, ElevenLabs provision

# Answers taken from the end-to-end run, kept short.
SENTENCES = {
    "wo1": ("wo", "Modou Diop dafa la ameel 1 550 FCFA."),
    "wo2": ("wo", "Saliou Wade moo la gëna ameel bor : 25 275 FCFA."),
    "wo3": ("wo", "Ci weer wii, ceeb moo gëna jaay, ba noppi mburu ak suukar."),
    "fr1": ("fr", "Saliou Wade vous doit le plus : 25 275 FCFA."),
}

# No TTS provider accepts the "wo" language code (ElevenLabs: unsupported_language), so
# Wolof text is sent under a carrier language; the multilingual models read the text.
CARRIER = {"wo": "fr", "fr": "fr"}

# variant -> (provider allowed, model, voice). None = Speko routing.
VARIANTS = {
    "auto": (None, None, None),
    "clone-v3": ("elevenlabs", "eleven_v3", CLONE),
    "clone-multi-v2": ("elevenlabs", "eleven_multilingual_v2", CLONE),
    "eleven-v3": ("elevenlabs", "eleven_v3", None),
    "gemini": ("google", None, None),  # Speko's TTS allowlist name for Gemini TTS
    "azure": ("azure", None, None),
}


def save(name: str, audio: bytes, content_type: str) -> Path:
    if content_type.startswith("audio/mpeg"):
        path = OUT / f"{name}.mp3"
        path.write_bytes(audio)
    elif content_type.startswith("audio/wav") or content_type.startswith("audio/x-wav"):
        path = OUT / f"{name}.wav"
        path.write_bytes(audio)
    else:  # raw PCM, e.g. audio/pcm;rate=24000: wrap it in a WAV header
        rate = 24000
        for part in content_type.split(";"):
            if part.strip().startswith("rate="):
                rate = int(part.split("=")[1])
        path = OUT / f"{name}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(audio)
    return path


def main() -> None:
    load_dotenv(BENCH.parent / "backend" / ".env")
    key = os.environ.get("SPEKO_API_KEY") or sys.exit("SPEKO_API_KEY absente de backend/.env")
    OUT.mkdir(exist_ok=True)
    only = set(sys.argv[1:])
    lines = []
    speko = Speko(api_key=key, timeout=90)
    try:
        for variant, (provider, model, voice) in VARIANTS.items():
            if only and variant not in only:
                continue
            constraints = (
                PipelineConstraints(allowedProviders=AllowedProviders(tts=[provider]))
                if provider
                else None
            )
            for sid, (lang, text) in SENTENCES.items():
                name = f"{variant}-{sid}"
                try:
                    r = speko.synthesize(
                        text,
                        language=CARRIER[lang],
                        voice=voice,
                        model=model,
                        constraints=constraints,
                    )
                except Exception as exc:
                    line = f"{name}: ERREUR {type(exc).__name__}: {str(exc)[:160]}"
                else:
                    path = save(name, r.audio, r.content_type)
                    line = f"{name}: {r.provider}/{r.model} -> {path.name}"
                print(line)
                lines.append(line)
    finally:
        speko.close()
    (OUT / "index.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
