"""Transcribe the bench recordings locally with Meta MMS (facebook/mms-1b-all).

    uv run --no-project --with torch --with transformers --with soundfile \
        python bench/mms.py

Nothing leaves the machine: the model runs on the CPU. Writes bench/results/mms.json.
"""

import json
import time
from pathlib import Path

import soundfile as sf
import torch
from transformers import AutoProcessor, Wav2Vec2ForCTC

BENCH = Path(__file__).resolve().parent
MODEL = "facebook/mms-1b-all"
# MMS uses ISO 639-3 codes, one language adapter each.
LANGS = {"wo": "wol", "fr": "fra", "en": "eng"}


def main() -> None:
    processor = AutoProcessor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL)
    model.eval()
    result: dict[str, object] = {"engine": "Meta MMS 1B (local, CPU)"}
    for lang, code in LANGS.items():
        processor.tokenizer.set_target_lang(code)
        model.load_adapter(code)
        transcripts = {}
        for wav in sorted((BENCH / "wav" / lang).glob("*.wav")):
            audio, rate = sf.read(wav, dtype="float32")
            assert rate == 16000, wav
            start = time.perf_counter()
            inputs = processor(audio, sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                logits = model(**inputs).logits
            text = processor.decode(torch.argmax(logits, dim=-1)[0])
            transcripts[wav.stem] = text
            print(f"{lang}/{wav.stem} ({time.perf_counter() - start:.1f} s): {text}")
        result[lang] = transcripts
    out = BENCH / "results" / "mms.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", out)


if __name__ == "__main__":
    main()
