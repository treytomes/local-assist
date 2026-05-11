import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import src.backend.router as router_mod


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cached health state before each test."""
    router_mod._azure_healthy = None
    router_mod._vertex_healthy = None
    router_mod._last_check = 0.0
    yield
    router_mod._azure_healthy = None
    router_mod._vertex_healthy = None
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


def test_resolve_preferred_vertex_returns_vertex():
    router_mod.set_provider_setting_fn(lambda: "vertex")
    try:
        provider, model = router_mod._resolve_provider_model("gpt-5.3-chat")
        assert provider == "vertex"
    finally:
        router_mod.set_provider_setting_fn(None)


def test_resolve_preferred_ollama_returns_ollama():
    router_mod.set_provider_setting_fn(lambda: "ollama")
    try:
        provider, model = router_mod._resolve_provider_model("gpt-5.3-chat")
        assert provider == "ollama"
        assert model == router_mod.ollama.DEFAULT_MODEL
    finally:
        router_mod.set_provider_setting_fn(None)


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


async def test_stream_chat_falls_back_to_vertex_when_azure_down():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=False)):
        with patch.object(router_mod.vertex, "health_check", new=AsyncMock(return_value=True)):
            with patch.object(router_mod.vertex, "stream_chat", return_value=AsyncMock()):
                provider, model, _ = await router_mod.stream_chat("gpt-5.3-chat", [])
    assert provider == "vertex"


async def test_stream_chat_falls_back_to_ollama_when_both_cloud_down():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=False)):
        with patch.object(router_mod.vertex, "health_check", new=AsyncMock(return_value=False)):
            with patch.object(router_mod.ollama, "ensure_model", new=AsyncMock()):
                with patch.object(router_mod.ollama, "stream_chat", return_value=AsyncMock()):
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

def _all_health_mocks(az: bool, vx: bool, ol: bool):
    """Context manager stack patching all three provider health checks."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(router_mod.azure,  "health_check", new=AsyncMock(return_value=az)))
    stack.enter_context(patch.object(router_mod.vertex, "health_check", new=AsyncMock(return_value=vx)))
    stack.enter_context(patch.object(router_mod.ollama, "health_check", new=AsyncMock(return_value=ol)))
    # local speech stubs
    from src.backend.providers import local_speech as ls
    stack.enter_context(patch.object(ls, "health_check_tts", new=AsyncMock(return_value=False)))
    stack.enter_context(patch.object(ls, "health_check_stt", new=AsyncMock(return_value=False)))
    return stack


async def test_get_health_all_up():
    with _all_health_mocks(True, True, True):
        result = await router_mod.get_health()
    assert result["azure"] is True
    assert result["vertex"] is True
    assert result["ollama"] is True
    assert result["active_provider"] == "azure"
    assert "preferred_provider" in result


async def test_get_health_azure_down_vertex_up():
    with _all_health_mocks(False, True, True):
        result = await router_mod.get_health()
    assert result["active_provider"] == "vertex"


async def test_get_health_azure_down_vertex_down():
    with _all_health_mocks(False, False, True):
        result = await router_mod.get_health()
    assert result["active_provider"] == "ollama"


async def test_get_health_all_down():
    with _all_health_mocks(False, False, False):
        result = await router_mod.get_health()
    assert result["active_provider"] == "none"


async def test_get_health_updates_cache():
    with _all_health_mocks(True, False, False):
        await router_mod.get_health()
    assert router_mod._azure_healthy is True
    assert router_mod._vertex_healthy is False
    assert router_mod._last_check > 0


# --- call_with_tools routing ---

async def test_call_with_tools_uses_azure():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=True)):
        with patch.object(router_mod.azure, "call_with_tools", new=AsyncMock(return_value={"role": "assistant"})):
            provider, model, msg = await router_mod.call_with_tools("gpt-5.3-chat", [], [])
    assert provider == "azure"
    assert msg["role"] == "assistant"


async def test_call_with_tools_uses_vertex_when_pinned():
    router_mod.set_provider_setting_fn(lambda: "vertex")
    try:
        with patch.object(router_mod.vertex, "call_with_tools", new=AsyncMock(return_value={"role": "assistant"})):
            provider, model, msg = await router_mod.call_with_tools("gpt-5.3-chat", [], [])
        assert provider == "vertex"
    finally:
        router_mod.set_provider_setting_fn(None)


async def test_call_with_tools_falls_back_to_ollama():
    with patch.object(router_mod.azure, "health_check", new=AsyncMock(return_value=False)):
        with patch.object(router_mod.vertex, "health_check", new=AsyncMock(return_value=False)):
            with patch.object(router_mod.ollama, "ensure_model", new=AsyncMock()):
                with patch.object(router_mod.ollama, "call_with_tools", new=AsyncMock(return_value={"role": "assistant"})):
                    provider, model, msg = await router_mod.call_with_tools("gpt-5.3-chat", [], [])
    assert provider == "ollama"


async def test_get_health_preferred_vertex_active():
    router_mod.set_provider_setting_fn(lambda: "vertex")
    try:
        with _all_health_mocks(True, True, True):
            result = await router_mod.get_health()
        assert result["active_provider"] == "vertex"
        assert result["preferred_provider"] == "vertex"
    finally:
        router_mod.set_provider_setting_fn(None)
