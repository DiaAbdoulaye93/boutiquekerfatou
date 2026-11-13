"""Play a recorded question through a running app, step by step, like the PWA does:
/api/transcribe, then /api/ask, then /api/speak. Prints when each step lands.

    uv run --no-project --with httpx python bench/try_voice.py http://localhost:8000 wo/02 fr/01

Writes the spoken answers to bench/results/voice-<lang>-<n>.<ext>. For a protected app,
set APP_USER and APP_PASSWORD in the environment.
"""

import os
import sys
import time
from pathlib import Path

import httpx

BENCH = Path(__file__).resolve().parent
EXT = {"audio/wav": "wav", "audio/mpeg": "mp3"}


def main() -> None:
    base, *items = sys.argv[1:]
    auth = None
    if os.environ.get("APP_PASSWORD"):
        auth = (os.environ.get("APP_USER", "boutique"), os.environ["APP_PASSWORD"])
    with httpx.Client(base_url=base, timeout=120, auth=auth) as client:
        for item in items:
            lang, num = item.split("/")
            ogg = sorted((BENCH / lang).glob("*.ogg"))[int(num) - 1]
            start = time.perf_counter()

            def at() -> str:
                return f"{time.perf_counter() - start:4.1f} s"  # noqa: B023

            heard = client.post(
                "/api/transcribe",
                files={"audio": (ogg.name, ogg.read_bytes(), "audio/ogg")},
                data={"language": lang},
            )
            if heard.status_code != 200:
                print(f"{item}: transcribe HTTP {heard.status_code} {heard.text[:200]}")
                continue
            question = heard.json()["text"]
            print(f"{item}\n  {at()}  entendu  : {question}")
            reply = client.post("/api/ask", json={"question": question, "history": []}).json()
            print(f"  {at()}  réponse  : [{reply['language']}] {reply['answer']}")
            print(f"           outils   : {[c['tool'] for c in reply['cards']]}")
            speech = client.post(
                "/api/speak", json={"text": reply["answer"], "language": reply["language"]}
            )
            if speech.status_code != 200:
                print(f"  {at()}  voix     : HTTP {speech.status_code} {speech.text[:200]}")
                continue
            kind = speech.headers["content-type"]
            out = BENCH / "results" / f"voice-{lang}-{num}.{EXT.get(kind, 'bin')}"
            out.write_bytes(speech.content)
            print(f"  {at()}  voix     : {kind} -> {out.name}")


if __name__ == "__main__":
    main()
