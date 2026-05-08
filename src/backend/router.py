"""
Provider router: tries Azure first; falls back to Ollama if Azure is unreachable.
Holds a cached health state so every request doesn't pay a round-trip.
"""
import asyncio
import time
from typing import AsyncIterator

from .providers import azure, ollama

OLLAMA_MODELS = {"gemma3:1b"}

_azure_healthy: bool | None = None
_last_check: float = 0.0
HEALTH_TTL = 30.0  # seconds between re-checks


async def _refresh_azure_health() -> bool:
    global _azure_healthy, _last_check
    result = await azure.health_check()
    _azure_healthy = result
    _last_check = time.monotonic()
    return result


async def azure_is_available() -> bool:
    global _azure_healthy, _last_check
    if _azure_healthy is None or (time.monotonic() - _last_check) > HEALTH_TTL:
        await _refresh_azure_health()
    return bool(_azure_healthy)


def _resolve_provider_model(requested_model: str) -> tuple[str, str]:
    """Return (provider, model). Ollama model is always gemma3:1b when falling back."""
    if requested_model in OLLAMA_MODELS:
        return "ollama", requested_model
    return "azure", requested_model


async def stream_chat(
    model: str,
    messages: list[dict],
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, str, AsyncIterator[dict]]:
    """
    Returns (provider, resolved_model, async_iterator).
    Falls back to Ollama + gemma3:1b if Azure is down.
    """
    provider, resolved = _resolve_provider_model(model)

    if provider == "azure":
        if not await azure_is_available():
            provider = "ollama"
            resolved = ollama.DEFAULT_MODEL
            await ollama.ensure_model(resolved)

    if provider == "ollama":
        return provider, resolved, ollama.stream_chat(resolved, messages, max_tokens, temperature)
    else:
        return provider, resolved, azure.stream_chat(resolved, messages, max_tokens, temperature)


async def get_health() -> dict:
    az = await azure.health_check()
    ol = await ollama.health_check()
    global _azure_healthy, _last_check
    _azure_healthy = az
    _last_check = time.monotonic()
    return {
        "azure": az,
        "ollama": ol,
        "active_provider": "azure" if az else ("ollama" if ol else "none"),
    }
