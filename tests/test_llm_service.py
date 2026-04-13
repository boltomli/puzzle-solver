"""Tests for LLMService — focusing on empty API key handling and list_models."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.services.config as config_mod
from src.services.llm_service import LLMService


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
        # Patch the models.list on the already-initialized client, then
        # prevent _ensure_client from recreating it during list_models()
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
