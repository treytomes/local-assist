import os
import json
from typing import AsyncIterator
import httpx

# Overridable by tests; empty string means "read from env at call time".
_INFERENCE_BASE: str = ""
API_KEY: str = ""
API_VER: str = "2024-08-01-preview"

EMBEDDING_MODEL = "text-embedding-3-small"


def _base() -> str:
    if _INFERENCE_BASE:
        return _INFERENCE_BASE
    raw = os.getenv("AZURE_INFERENCE_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT", "")
    raw = raw.rstrip("/")
    if raw.endswith("/openai/v1"):
        raw = raw[: -len("/openai/v1")]
    return raw


def _key() -> str:
    return API_KEY or os.getenv("AZURE_API_KEY", "")


def _headers() -> dict:
    return {
        "api-key": _key(),
        "Content-Type": "application/json",
    }


def _deployment_url(deployment: str, path: str) -> str:
    return f"{_base()}/openai/deployments/{deployment}/{path}?api-version={API_VER}"


async def health_check() -> bool:
    # A lightweight probe: HEAD against the chat endpoint of the primary model.
    url = _deployment_url("Mistral-Large-3", "chat/completions")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            # POST with minimal payload; any non-5xx/network response means reachable.
            r = await client.post(
                url,
                headers=_headers(),
                json={"messages": [{"role": "user", "content": "hi"}], "max_completion_tokens": 1},
            )
            return r.status_code < 500
    except Exception:
        return False


# Models that use max_completion_tokens and do not support temperature overrides.
_GPT_MODELS = {"gpt-5.3-chat", "gpt-4o", "gpt-4o-mini", "o1", "o3", "o4"}


def _is_gpt(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in _GPT_MODELS)


def _chat_payload(model: str, messages: list[dict], max_tokens: int, temperature: float) -> dict:
    payload: dict = {
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if _is_gpt(model):
        # GPT-5 series: uses max_completion_tokens, temperature must be omitted
        # (only default value of 1 is accepted).
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = temperature
    return payload


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
    url = _deployment_url(model, "chat/completions")
    payload = _chat_payload(model, messages, max_tokens, temperature)

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            async with client.stream("POST", url, headers=_headers(), json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield {"type": "error", "message": f"Azure HTTP {resp.status_code}: {body.decode()[:200]}"}
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
                    # Process content before usage — Mistral often puts the last
                    # token and usage in the same chunk; the old `continue` dropped it.
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content")
                        if text:
                            yield {"type": "delta", "content": text}
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        yield {
                            "type": "usage",
                            "prompt_tokens": u.get("prompt_tokens", 0),
                            "completion_tokens": u.get("completion_tokens", 0),
                        }
        except httpx.RequestError as exc:
            yield {"type": "error", "message": str(exc)}


async def call_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 2048,
) -> dict:
    """
    Non-streaming call that includes tool definitions.
    Returns the raw message dict from the first choice:
      {"role": "assistant", "content": ..., "tool_calls": [...] | None}
    """
    url = _deployment_url(model, "chat/completions")
    payload: dict = {
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }
    if _is_gpt(model):
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers=_headers(), json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"Azure HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        return data["choices"][0]["message"]


async def get_embedding(text: str) -> list[float]:
    url = _deployment_url(EMBEDDING_MODEL, "embeddings")
    payload = {"input": text}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
