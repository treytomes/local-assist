"""
Azure TTS and STT providers.

TTS: POST /openai/deployments/gpt-4o-mini-tts/audio/speech
STT: POST /openai/deployments/gpt-4o-transcribe/audio/transcriptions
"""
from __future__ import annotations

import os
import httpx

from .azure import _base, _key, API_VER

TTS_MODEL = "gpt-4o-mini-tts"
STT_MODEL = "gpt-4o-transcribe"

VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")


def _tts_url() -> str:
    return f"{_base()}/openai/deployments/{TTS_MODEL}/audio/speech?api-version={API_VER}"


def _stt_url() -> str:
    return f"{_base()}/openai/deployments/{STT_MODEL}/audio/transcriptions?api-version={API_VER}"


def _auth_headers() -> dict:
    return {"api-key": _key()}


async def synthesize(text: str, voice: str = "alloy", speed: float = 1.0) -> bytes:
    """
    Convert text to speech. Returns raw MP3 bytes.
    voice: one of alloy, echo, fable, onyx, nova, shimmer
    speed: 0.25–4.0
    """
    if voice not in VOICES:
        voice = "alloy"
    payload = {
        "model": TTS_MODEL,
        "input": text,
        "voice": voice,
        "speed": max(0.25, min(4.0, speed)),
        "response_format": "mp3",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            _tts_url(),
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code != 200:
            body = resp.text[:300]
            raise RuntimeError(f"TTS HTTP {resp.status_code}: {body}")
        return resp.content


async def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Transcribe audio bytes. Returns the transcript string.
    filename hint tells Azure the container format.
    """
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            _stt_url(),
            headers=_auth_headers(),
            files={"file": (filename, audio_bytes, "audio/webm")},
            data={"model": STT_MODEL, "response_format": "json"},
        )
        if resp.status_code != 200:
            body = resp.text[:300]
            raise RuntimeError(f"STT HTTP {resp.status_code}: {body}")
        return resp.json().get("text", "")
