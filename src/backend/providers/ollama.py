import json
import subprocess
from typing import AsyncIterator
import httpx

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:1b"


def _normalize_messages(messages: list[dict]) -> list[dict]:
    """
    Ollama's native /api/chat API differs from OpenAI format in two ways:
    - content must be a string (not null)
    - tool_call arguments must be a JSON object (dict), not a JSON-encoded string
    """
    result = []
    for msg in messages:
        msg = dict(msg)
        if msg.get("content") is None:
            msg["content"] = ""
        if msg.get("tool_calls"):
            calls = []
            for tc in msg["tool_calls"]:
                tc = dict(tc)
                fn = dict(tc.get("function", {}))
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        fn["arguments"] = json.loads(args)
                    except (json.JSONDecodeError, ValueError):
                        fn["arguments"] = {}
                tc["function"] = fn
                calls.append(tc)
            msg["tool_calls"] = calls
        result.append(msg)
    return result


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


async def call_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 2048,
) -> dict:
    """
    Non-streaming tool call. Returns the assistant message dict in OpenAI format:
      {"role": "assistant", "content": ..., "tool_calls": [...] | None}
    Arguments are serialized back to JSON strings to match OpenAI convention.
    """
    url = f"{OLLAMA_BASE}/api/chat"
    payload = {
        "model": model,
        "messages": _normalize_messages(messages),
        "tools": tools,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        msg = data["message"]
        # Ollama returns arguments as a dict; re-serialize to string for OpenAI compat
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                if isinstance(fn.get("arguments"), dict):
                    fn["arguments"] = json.dumps(fn["arguments"])
        return msg


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
        "messages": _normalize_messages(messages),
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
