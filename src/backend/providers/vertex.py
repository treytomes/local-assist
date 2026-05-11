"""
Vertex AI provider — Mistral Large 3 via Google Cloud Model Garden.

Mistral models on Vertex use the publisher endpoint pattern, not the
OpenAI-compatibility gateway (/endpoints/openai) which is Gemini-only:

  Streaming:     POST https://{region}-aiplatform.googleapis.com/v1/projects/{project}/
                     locations/{region}/publishers/mistralai/models/{model}:streamRawPredict
  Non-streaming: POST .../models/{model}:rawPredict

The request body and response format are OpenAI-compatible.

Auth: Google Application Default Credentials (ADC) with the
cloud-platform scope.

Environment variables (all optional; defaults below):
  GCP_PROJECT   — GCP project ID (falls back to ADC-inferred project)
  VERTEX_REGION — deployment region (default: us-south1)
"""
from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model / endpoint config
# ---------------------------------------------------------------------------

# Short model name used in the publisher endpoint path.
PUBLISHER = "mistralai"
MODEL_NAME = "mistral-large-3"
# Version name passed in the request body (required by the rawPredict API).
MODEL_VERSION = "mistralai/mistral-large-3-instruct-2512"

# Overridable by tests
_PROJECT_OVERRIDE: str = ""
_REGION_OVERRIDE: str = ""


def _project() -> str:
    if _PROJECT_OVERRIDE:
        return _PROJECT_OVERRIDE
    if os.getenv("GCP_PROJECT"):
        return os.environ["GCP_PROJECT"]
    try:
        import google.auth
        _, project = google.auth.default()
        return project or ""
    except Exception:
        return ""


def _region() -> str:
    return _REGION_OVERRIDE or os.getenv("VERTEX_REGION", "us-south1")


def _base_url() -> str:
    region = _region()
    project = _project()
    return (
        f"https://{region}-aiplatform.googleapis.com/v1"
        f"/projects/{project}/locations/{region}"
        f"/publishers/{PUBLISHER}/models/{MODEL_NAME}"
    )


def _stream_url() -> str:
    return f"{_base_url()}:streamRawPredict"


def _predict_url() -> str:
    return f"{_base_url()}:rawPredict"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_token() -> str:
    """Return a fresh ADC Bearer token with the cloud-platform scope."""
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def health_check() -> bool:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(
                _predict_url(),
                headers=_headers(),
                json={
                    "model": MODEL_VERSION,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                    "stream": False,
                },
            )
            # 404 = model not yet accessible (quota pending); treat as unhealthy, not error
            return r.status_code == 200 or (r.status_code not in (404, 403) and r.status_code < 500)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Chat payload helpers
# ---------------------------------------------------------------------------

def _stream_payload(messages: list[dict], max_tokens: int, temperature: float) -> dict:
    return {
        "model": MODEL_VERSION,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }


# ---------------------------------------------------------------------------
# Streaming chat
# ---------------------------------------------------------------------------

async def stream_chat(
    model: str,
    messages: list[dict],
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> AsyncIterator[dict]:
    """
    Yields dicts:
      {"type": "delta",   "content": str}
      {"type": "usage",   "prompt_tokens": int, "completion_tokens": int}
      {"type": "error",   "message": str}
    """
    url = _stream_url()
    payload = _stream_payload(messages, max_tokens, temperature)

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            async with client.stream("POST", url, headers=_headers(), json=payload) as resp:
                if resp.status_code == 500:
                    await resp.aread()
                    async for item in _non_streaming_fallback(client, payload):
                        yield item
                    return
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield {"type": "error", "message": f"Vertex HTTP {resp.status_code}: {body.decode()[:400]}"}
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        content = delta.get("content")
                        if isinstance(content, list):
                            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                        if content:
                            yield {"type": "delta", "content": content}
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        yield {
                            "type": "usage",
                            "prompt_tokens": u.get("prompt_tokens", 0),
                            "completion_tokens": u.get("completion_tokens", 0),
                        }
        except httpx.RequestError as exc:
            yield {"type": "error", "message": str(exc)}


async def _non_streaming_fallback(
    client: httpx.AsyncClient, streaming_payload: dict
) -> AsyncIterator[dict]:
    payload = {k: v for k, v in streaming_payload.items() if k not in ("stream", "stream_options")}
    payload["stream"] = False
    url = _predict_url()
    try:
        r = await client.post(url, headers=_headers(), json=payload, timeout=120)
        if r.status_code != 200:
            yield {"type": "error", "message": f"Vertex HTTP {r.status_code} (fallback): {r.text[:400]}"}
            return
        data = r.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if content:
            yield {"type": "delta", "content": content}
        if data.get("usage"):
            u = data["usage"]
            yield {
                "type": "usage",
                "prompt_tokens": u.get("prompt_tokens", 0),
                "completion_tokens": u.get("completion_tokens", 0),
            }
    except Exception as exc:
        yield {"type": "error", "message": f"Vertex fallback error: {exc}"}


# ---------------------------------------------------------------------------
# Tool-use (non-streaming)
# ---------------------------------------------------------------------------

async def call_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 2048,
) -> dict:
    """
    Non-streaming call with tool definitions.
    Returns the raw message dict from the first choice.
    """
    payload = {
        "model": MODEL_VERSION,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(_predict_url(), headers=_headers(), json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"Vertex HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
        return data["choices"][0]["message"]
