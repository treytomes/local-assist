import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import src.backend.router as router_mod


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cached health state before each test."""
    router_mod._azure_healthy = None
    router_mod._last_check = 0.0
    yield
    router_mod._azure_healthy = None
    router_mod._last_check = 0.0


# --- _resolve_provider_model ---

def test_resolve_azure_model():
    provider, model = router_mod._resolve_provider_model("gpt-5.3-chat")
    assert provider == "azure"
    assert model == "gpt-5.3-chat"


def test_resolve_ollama_model():
    provider, model = router_mod._resolve_provider_model("gemma3:1b")
    assert provider == "ollama"
    assert model == "gemma3:1b"


def test_resolve_unknown_model_defaults_azure():
    provider, model = router_mod._resolve_provider_model("some-future-model")
    assert provider == "azure"


# --- azure_is_available (caching) ---

async def test_azure_is_available_checks_when_none():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=True)):
        result = await router_mod.azure_is_available()
    assert result is True
    assert router_mod._azure_healthy is True


async def test_azure_is_available_uses_cache():
    router_mod._azure_healthy = True
    router_mod._last_check = time.monotonic()  # fresh
    with patch.object(router_mod.azure, "health_check", new=AsyncMock()) as mock_hc:
        result = await router_mod.azure_is_available()
        mock_hc.assert_not_called()
    assert result is True


async def test_azure_is_available_refreshes_stale_cache():
    router_mod._azure_healthy = True
    router_mod._last_check = time.monotonic() - 9999  # expired
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=False)):
        result = await router_mod.azure_is_available()
    assert result is False


# --- stream_chat routing ---

async def test_stream_chat_uses_azure_when_healthy():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=True)):
        with patch.object(router_mod.azure, "stream_chat", return_value=AsyncMock()) as mock_az:
            provider, model, _ = await router_mod.stream_chat("gpt-5.3-chat", [])
    assert provider == "azure"
    assert model == "gpt-5.3-chat"


async def test_stream_chat_falls_back_to_ollama_when_azure_down():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=False)):
        with patch.object(router_mod.ollama, "ensure_model", new=AsyncMock()):
            with patch.object(router_mod.ollama, "stream_chat", return_value=AsyncMock()) as mock_ol:
                provider, model, _ = await router_mod.stream_chat("gpt-5.3-chat", [])
    assert provider == "ollama"
    assert model == router_mod.ollama.DEFAULT_MODEL


async def test_stream_chat_ollama_model_skips_azure_check():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock()) as mock_hc:
        with patch.object(router_mod.ollama, "stream_chat", return_value=AsyncMock()):
            provider, model, _ = await router_mod.stream_chat("gemma3:1b", [])
    mock_hc.assert_not_called()
    assert provider == "ollama"


# --- get_health ---

async def test_get_health_both_up():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=True)):
        with patch.object(router_mod.ollama, "health_check", new=AsyncMock(return_value=True)):
            result = await router_mod.get_health()
    assert result["azure"] is True
    assert result["ollama"] is True
    assert result["active_provider"] == "azure"


async def test_get_health_azure_down():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=False)):
        with patch.object(router_mod.ollama, "health_check", new=AsyncMock(return_value=True)):
            result = await router_mod.get_health()
    assert result["active_provider"] == "ollama"


async def test_get_health_both_down():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=False)):
        with patch.object(router_mod.ollama, "health_check", new=AsyncMock(return_value=False)):
            result = await router_mod.get_health()
    assert result["active_provider"] == "none"


async def test_get_health_updates_cache():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=True)):
        with patch.object(router_mod.ollama, "health_check", new=AsyncMock(return_value=False)):
            await router_mod.get_health()
    assert router_mod._azure_healthy is True
    assert router_mod._last_check > 0
