import json
import subprocess
from typing import AsyncIterator
import httpx

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:1b"


async def health_check() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def ensure_model(model: str = DEFAULT_MODEL) -> None:
    """Pull model if not already present. Blocks until done."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            if r.status_code == 200:
                names = [m["name"] for m in r.json().get("models", [])]
                if any(n.startswith(model.split(":")[0]) for n in names):
                    return
        # Pull in a subprocess so we don't block the event loop for the full download.
        # Fire-and-forget; the next health check will confirm availability.
        subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


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
    url = f"{OLLAMA_BASE}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield {"type": "error", "message": f"Ollama HTTP {resp.status_code}: {body.decode()[:200]}"}
                    return
                prompt_tokens = 0
                completion_tokens = 0
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = chunk.get("message", {})
                    text = msg.get("content", "")
                    if text:
                        yield {"type": "delta", "content": text}
                    if chunk.get("done"):
                        prompt_tokens     = chunk.get("prompt_eval_count", 0)
                        completion_tokens = chunk.get("eval_count", 0)
                yield {
                    "type": "usage",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
        except httpx.RequestError as exc:
            yield {"type": "error", "message": str(exc)}
