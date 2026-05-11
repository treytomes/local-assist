"""
Provider router: Azure → Vertex AI → Ollama fallback chain.

Manual override: set the 'chat_provider' key in the settings table to
'azure', 'vertex', or 'ollama' to pin to a specific provider.
'auto' (default) uses the priority chain.
"""
import asyncio
import time
from typing import AsyncIterator

from .providers import azure, ollama, vertex
from .providers import local_speech as _local_speech

OLLAMA_MODELS = {"gemma3:1b"}

_azure_healthy: bool | None = None
_vertex_healthy: bool | None = None
_last_check: float = 0.0
HEALTH_TTL = 30.0

# Injected by main.py after DB is ready
_get_chat_provider_setting: "callable | None" = None


def set_provider_setting_fn(fn: "callable") -> None:
    """Register the function main.py uses to read the chat_provider setting."""
    global _get_chat_provider_setting
    _get_chat_provider_setting = fn


def _preferred_provider() -> str:
    """Return the manually pinned provider, or 'auto'."""
    if _get_chat_provider_setting:
        v = _get_chat_provider_setting()
        if v in ("azure", "vertex", "ollama", "auto"):
            return v
    return "auto"


async def _refresh_health() -> tuple[bool, bool]:
    global _azure_healthy, _vertex_healthy, _last_check
    az, vx = await asyncio.gather(azure.health_check(), vertex.health_check())
    _azure_healthy = az
    _vertex_healthy = vx
    _last_check = time.monotonic()
    return az, vx


async def _ensure_health_fresh() -> tuple[bool, bool]:
    global _azure_healthy, _vertex_healthy
    if _azure_healthy is None or (time.monotonic() - _last_check) > HEALTH_TTL:
        return await _refresh_health()
    return bool(_azure_healthy), bool(_vertex_healthy)


async def azure_is_available() -> bool:
    az, _ = await _ensure_health_fresh()
    return az


def _resolve_provider_model(requested_model: str) -> tuple[str, str]:
    if requested_model in OLLAMA_MODELS:
        return "ollama", requested_model
    preferred = _preferred_provider()
    if preferred == "vertex":
        return "vertex", requested_model
    if preferred == "ollama":
        return "ollama", ollama.DEFAULT_MODEL
    return "azure", requested_model


async def _pick_cloud_provider() -> str:
    """
    In 'auto' mode: try Azure first, then Vertex, then Ollama.
    Returns the name of the first healthy cloud provider, or 'ollama'.
    """
    az, vx = await _ensure_health_fresh()
    if az:
        return "azure"
    if vx:
        return "vertex"
    return "ollama"


async def stream_chat(
    model: str,
    messages: list[dict],
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, str, AsyncIterator[dict]]:
    """Returns (provider, resolved_model, async_iterator)."""
    provider, resolved = _resolve_provider_model(model)

    if provider == "azure":
        preferred = _preferred_provider()
        if preferred == "auto":
            provider = await _pick_cloud_provider()
            if provider == "ollama":
                resolved = ollama.DEFAULT_MODEL
                await ollama.ensure_model(resolved)
        elif not (await azure_is_available()):
            provider = "ollama"
            resolved = ollama.DEFAULT_MODEL
            await ollama.ensure_model(resolved)

    if provider == "vertex":
        return provider, resolved, vertex.stream_chat(resolved, messages, max_tokens, temperature)
    if provider == "ollama":
        return provider, resolved, ollama.stream_chat(resolved, messages, max_tokens, temperature)
    return provider, resolved, azure.stream_chat(resolved, messages, max_tokens, temperature)


async def call_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int = 2048,
) -> tuple[str, str, dict]:
    """Returns (provider, resolved_model, assistant_message_dict)."""
    provider, resolved = _resolve_provider_model(model)

    if provider == "azure":
        preferred = _preferred_provider()
        if preferred == "auto":
            provider = await _pick_cloud_provider()
            if provider == "ollama":
                resolved = ollama.DEFAULT_MODEL
                await ollama.ensure_model(resolved)
        elif not (await azure_is_available()):
            provider = "ollama"
            resolved = ollama.DEFAULT_MODEL
            await ollama.ensure_model(resolved)

    if provider == "vertex":
        msg = await vertex.call_with_tools(resolved, messages, tools, max_tokens)
    elif provider == "ollama":
        msg = await ollama.call_with_tools(resolved, messages, tools, max_tokens)
    else:
        msg = await azure.call_with_tools(resolved, messages, tools, max_tokens)
    return provider, resolved, msg


async def get_health() -> dict:
    az, vx, ol, local_tts, local_stt = await asyncio.gather(
        azure.health_check(),
        vertex.health_check(),
        ollama.health_check(),
        _local_speech.health_check_tts(),
        _local_speech.health_check_stt(),
    )
    global _azure_healthy, _vertex_healthy, _last_check
    _azure_healthy = az
    _vertex_healthy = vx
    _last_check = time.monotonic()

    preferred = _preferred_provider()
    if preferred == "auto":
        active = "azure" if az else ("vertex" if vx else ("ollama" if ol else "none"))
    elif preferred == "vertex":
        active = "vertex" if vx else ("azure" if az else ("ollama" if ol else "none"))
    elif preferred == "ollama":
        active = "ollama" if ol else "none"
    else:
        active = "azure" if az else ("vertex" if vx else ("ollama" if ol else "none"))

    return {
        "azure": az,
        "vertex": vx,
        "ollama": ol,
        "local_tts": local_tts,
        "local_stt": local_stt,
        "active_provider": active,
        "preferred_provider": preferred,
    }
