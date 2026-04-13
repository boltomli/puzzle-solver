"""Tests for LLMService — focusing on empty API key handling and list_models."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.services.config as config_mod
from src.services.llm_service import LLMService, _is_local_url


class TestIsLocalUrl:
    """Unit tests for the _is_local_url() helper."""

    # --- should be detected as local ---
    @pytest.mark.parametrize("url", [
        "http://localhost:1234/v1",
        "http://127.0.0.1:11434/v1",
        "http://127.0.0.1/v1",
        "http://[::1]/v1",              # IPv6 loopback — correct URL syntax
        "http://lmac:1234/v1",          # single-label intranet hostname
        "http://myserver/v1",            # single-label, no dots
        "http://10.0.0.5:8080/v1",      # RFC-1918 class A
        "http://172.16.0.1/v1",         # RFC-1918 class B lower bound
        "http://172.31.255.255/v1",     # RFC-1918 class B upper bound
        "http://192.168.1.100:1234/v1", # RFC-1918 class C
        "http://169.254.0.1/v1",        # link-local
    ])
    def test_local_urls(self, url):
        assert _is_local_url(url) is True, f"expected local: {url}"

    # --- should NOT be detected as local (public / remote) ---
    @pytest.mark.parametrize("url", [
        "https://api.openai.com/v1",
        "https://api.anthropic.com/v1",
        "https://openrouter.ai/api/v1",
        "http://my-vps.example.com:8080/v1",  # multi-label hostname → public
        "http://8.8.8.8/v1",                  # Google DNS — globally routable
        "http://1.1.1.1/v1",                  # Cloudflare DNS — globally routable
    ])
    def test_public_urls(self, url):
        assert _is_local_url(url) is False, f"expected public: {url}"

    # --- edge cases ---
    def test_empty_string(self):
        assert _is_local_url("") is False

    def test_invalid_url(self):
        # Should not raise, just return False
        assert _is_local_url("not-a-url") is False


class TestEnsureClient:
    """Tests for _ensure_client method."""

    def test_raises_without_base_url(self, tmp_path, monkeypatch):
        """Should raise ValueError when api_base_url is missing."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"api_base_url": "", "api_key": "key", "model": "m"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        with pytest.raises(ValueError, match="API Base URL"):
            llm._ensure_client()

    def test_works_with_empty_api_key(self, tmp_path, monkeypatch):
        """Should succeed with empty api_key, falling back to 'no-key'."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api_base_url": "http://localhost:11434/v1",
                "api_key": "",
                "model": "llama3",
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        assert llm.client is not None
        assert llm.model == "llama3"
        # The OpenAI client should have been created with "no-key" as fallback
        assert llm.client.api_key == "no-key"

    def test_works_with_real_api_key(self, tmp_path, monkeypatch):
        """Should use the provided api_key when it is non-empty."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api_base_url": "https://api.openai.com/v1",
                "api_key": "sk-test123",
                "model": "gpt-4",
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        assert llm.client is not None
        assert llm.model == "gpt-4"
        assert llm.client.api_key == "sk-test123"

    def test_default_model_when_empty(self, tmp_path, monkeypatch):
        """Should default to 'gpt-4' when model is empty."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api_base_url": "https://api.openai.com/v1",
                "api_key": "key",
                "model": "",
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        assert llm.model == "gpt-4"

    def test_local_url_bypasses_proxy(self, tmp_path, monkeypatch):
        """Local base_url should use no-proxy transport."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api_base_url": "http://lmac:1234/v1",
                "api_key": "",
                "model": "gemma",
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        with patch("src.services.llm_service._build_http_client") as mock_build:
            mock_build.return_value = MagicMock(spec=__import__("httpx").AsyncClient)
            llm = LLMService()
            llm._ensure_client()
            mock_build.assert_called_once_with("http://lmac:1234/v1")

    def test_public_url_uses_system_proxy(self, tmp_path, monkeypatch):
        """Public base_url should use the default httpx client (system proxy)."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api_base_url": "https://api.openai.com/v1",
                "api_key": "sk-abc",
                "model": "gpt-4",
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        with patch("src.services.llm_service._build_http_client") as mock_build:
            mock_build.return_value = MagicMock(spec=__import__("httpx").AsyncClient)
            llm = LLMService()
            llm._ensure_client()
            mock_build.assert_called_once_with("https://api.openai.com/v1")


class TestListModels:
    """Tests for list_models method."""

    @pytest.mark.asyncio
    async def test_list_models_returns_sorted_ids(self, tmp_path, monkeypatch):
        """Should return a sorted list of model IDs."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api_base_url": "http://localhost:11434/v1",
                "api_key": "",
                "model": "llama3",
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        # Mock the models.list() response
        mock_model_a = MagicMock()
        mock_model_a.id = "zephyr"
        mock_model_b = MagicMock()
        mock_model_b.id = "llama3"
        mock_model_c = MagicMock()
        mock_model_c.id = "codestral"

        mock_response = MagicMock()
        mock_response.data = [mock_model_a, mock_model_b, mock_model_c]

        llm = LLMService()
        llm._ensure_client()
        llm.client.models.list = AsyncMock(return_value=mock_response)
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)

        result = await llm.list_models()
        assert result == ["codestral", "llama3", "zephyr"]

    @pytest.mark.asyncio
    async def test_list_models_empty_response(self, tmp_path, monkeypatch):
        """Should return empty list when no models available."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "api_base_url": "http://localhost:11434/v1",
                "api_key": "",
                "model": "llama3",
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        mock_response = MagicMock()
        mock_response.data = []

        llm = LLMService()
        llm._ensure_client()
        llm.client.models.list = AsyncMock(return_value=mock_response)
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)

        result = await llm.list_models()
        assert result == []
