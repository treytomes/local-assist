"""
Azure contract stubs for M2 (Speech I/O) and M4 (Vision) models.

These tests are skipped with pytest.skip() until the provider methods are
implemented.  They serve as a spec: each stub describes the expected behaviour
and the deployment name so nothing is forgotten when the milestone lands.

Models covered:
  M2 — gpt-4o-mini-tts  (text-to-speech, 6 voices)
  M2 — gpt-4o-transcribe (speech-to-text)
  M2 — gpt-realtime      (bidirectional realtime voice via WebSocket)
  M4 — gpt-4o            (vision — multimodal image input)
"""
import base64
import os
import wave
import struct

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.azure]

NOT_IMPLEMENTED = "Provider method not yet implemented (milestone not reached)"

TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


# ---------------------------------------------------------------------------
# Helpers (used once methods exist)
# ---------------------------------------------------------------------------

def _minimal_png_b64() -> str:
    """Return a base64-encoded 1×1 red PNG for vision tests."""
    # Minimal valid PNG bytes for a 1x1 red pixel
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"                          # signature
        b"\x00\x00\x00\rIHDR"                          # IHDR length + type
        b"\x00\x00\x00\x01\x00\x00\x00\x01"           # 1×1
        b"\x08\x02\x00\x00\x00\x90wS\xde"             # 8-bit RGB + CRC
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"     # IDAT
        b"\x00\x01\x01\x00\x05\x18\xd8N"              # 1 red pixel compressed
        b"\x00\x00\x00\x00IEND\xaeB`\x82"             # IEND
    )
    return base64.b64encode(png_bytes).decode()


def _silent_wav_bytes(duration_ms: int = 100) -> bytes:
    """Return bytes of a minimal silent WAV file (16-bit mono 16 kHz)."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration_ms / 1000)
    buf = struct.pack(f"<{num_samples}h", *([0] * num_samples))
    import io
    f = io.BytesIO()
    with wave.open(f, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(buf)
    return f.getvalue()


# ---------------------------------------------------------------------------
# M2 — Text-to-Speech (gpt-4o-mini-tts)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("voice", TTS_VOICES)
async def test_tts_voice_returns_audio(require_azure, voice):
    """
    gpt-4o-mini-tts should accept a text + voice parameter and return audio bytes.

    Expected provider method (to be added to azure.py):
        async def synthesize_speech(text: str, voice: str) -> bytes

    Deployment: gpt-4o-mini-tts
    Endpoint:   POST /openai/deployments/gpt-4o-mini-tts/audio/speech
    Payload:    {"model": "tts-1", "input": <text>, "voice": <voice>}
    Response:   raw audio bytes (mp3 or opus)
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_tts_returns_non_empty_bytes(require_azure):
    """Audio response for any voice should be non-empty bytes."""
    pytest.skip(NOT_IMPLEMENTED)


async def test_tts_different_voices_differ(require_azure):
    """
    The same text synthesized with two different voices should produce
    different audio bytes (verifies voice parameter is respected).
    """
    pytest.skip(NOT_IMPLEMENTED)


# ---------------------------------------------------------------------------
# M2 — Speech-to-Text (gpt-4o-transcribe)
# ---------------------------------------------------------------------------

async def test_stt_transcribes_audio(require_azure):
    """
    gpt-4o-transcribe should accept audio bytes and return a transcript string.

    Expected provider method:
        async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> str

    Deployment: gpt-4o-transcribe
    Endpoint:   POST /openai/deployments/gpt-4o-transcribe/audio/transcriptions
    Payload:    multipart/form-data with file + model fields
    Response:   {"text": "<transcript>"}
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_stt_returns_string(require_azure):
    """Transcript result should be a non-empty str."""
    pytest.skip(NOT_IMPLEMENTED)


async def test_stt_silent_audio_returns_empty_or_string(require_azure):
    """
    A silent WAV should either return an empty string or a short filler
    (not raise an exception).
    """
    pytest.skip(NOT_IMPLEMENTED)


# ---------------------------------------------------------------------------
# M2 — Realtime voice (gpt-realtime)
# ---------------------------------------------------------------------------

async def test_realtime_websocket_connects(require_azure):
    """
    gpt-realtime should accept a WebSocket upgrade at:
        wss://<host>/openai/realtime?api-version=...&model=gpt-realtime
    and return a session.created event within a few seconds.

    Expected provider method:
        async def open_realtime_session(...) -> WebSocketSession
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_realtime_session_created_event_shape(require_azure):
    """
    The first message from gpt-realtime should be a JSON object with
    {"type": "session.created", "session": {...}}.
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_realtime_sends_and_receives_audio(require_azure):
    """
    A minimal audio chunk sent over the realtime WebSocket should elicit
    at least one response.audio.delta event back.
    """
    pytest.skip(NOT_IMPLEMENTED)


# ---------------------------------------------------------------------------
# M4 — Vision (gpt-4o multimodal)
# ---------------------------------------------------------------------------

async def test_vision_accepts_image_url(require_azure):
    """
    gpt-4o should accept a message with an image_url content part and return
    a text response describing the image.

    Uses the existing stream_chat path — no new provider method needed;
    the message payload just includes a vision content block.
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_vision_accepts_base64_image(require_azure):
    """
    gpt-4o should accept a base64-encoded image in the message content and
    return a non-empty text response.

    Payload shape:
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64,<b64>"}},
            {"type": "text", "text": "What colour is this pixel?"}
        ]}
    """
    pytest.skip(NOT_IMPLEMENTED)


async def test_vision_response_references_image(require_azure):
    """
    When asked 'What colour is this pixel?' for a solid-red image, the
    response should contain the word 'red' (case-insensitive).
    """
    pytest.skip(NOT_IMPLEMENTED)
