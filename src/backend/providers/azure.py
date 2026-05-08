import os
import json
from typing import AsyncIterator
import httpx

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")  # e.g. https://....openai.azure.com/openai/v1
API_KEY  = os.getenv("AZURE_API_KEY", "")
API_VER  = "2025-04-01-preview"

EMBEDDING_MODEL = "text-embedding-3-small"


def _headers() -> dict:
    return {
        "api-key": API_KEY,
        "Content-Type": "application/json",
    }


async def health_check() -> bool:
    url = f"{ENDPOINT.rstrip('/')}/models?api-version={API_VER}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, headers=_headers())
            return r.status_code == 200
    except Exception:
        return False


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
    url = f"{ENDPOINT.rstrip('/')}/chat/completions?api-version={API_VER}"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

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
                    # usage chunk (last chunk before [DONE])
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        yield {
                            "type": "usage",
                            "prompt_tokens": u.get("prompt_tokens", 0),
                            "completion_tokens": u.get("completion_tokens", 0),
                        }
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content")
                        if text:
                            yield {"type": "delta", "content": text}
        except httpx.RequestError as exc:
            yield {"type": "error", "message": str(exc)}


async def get_embedding(text: str) -> list[float]:
    url = f"{ENDPOINT.rstrip('/')}/embeddings?api-version={API_VER}"
    payload = {"model": EMBEDDING_MODEL, "input": text}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
