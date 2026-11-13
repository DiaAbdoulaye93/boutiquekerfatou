"""Copy of app.voice.client.playable, so bench scripts run without the backend env."""

import io
import wave


def playable(audio: bytes, content_type: str) -> tuple[bytes, str]:
    base, *params = [part.strip() for part in content_type.split(";")]
    if base not in ("audio/pcm", "audio/l16", "audio/raw"):
        return audio, content_type
    rate = 24000
    for param in params:
        if param.startswith("rate="):
            rate = int(param.removeprefix("rate="))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(audio)
    return buffer.getvalue(), "audio/wav"
