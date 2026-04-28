"""Tests for LLMService — focusing on empty API key handling and list_models."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.services.config as config_mod
from src.services.llm_service import LLMService, _is_local_url


class TestIsLocalUrl:
    """Unit tests for the _is_local_url() helper."""

    # --- should be detected as local ---
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:1234/v1",
            "http://127.0.0.1:11434/v1",
            "http://127.0.0.1/v1",
            "http://[::1]/v1",  # IPv6 loopback — correct URL syntax
            "http://lmac:1234/v1",  # single-label intranet hostname
            "http://myserver/v1",  # single-label, no dots
            "http://10.0.0.5:8080/v1",  # RFC-1918 class A
            "http://172.16.0.1/v1",  # RFC-1918 class B lower bound
            "http://172.31.255.255/v1",  # RFC-1918 class B upper bound
            "http://192.168.1.100:1234/v1",  # RFC-1918 class C
            "http://169.254.0.1/v1",  # link-local
        ],
    )
    def test_local_urls(self, url):
        assert _is_local_url(url) is True, f"expected local: {url}"

    # --- should NOT be detected as local (public / remote) ---
    @pytest.mark.parametrize(
        "url",
        [
            "https://api.openai.com/v1",
            "https://api.anthropic.com/v1",
            "https://openrouter.ai/api/v1",
            "http://my-vps.example.com:8080/v1",  # multi-label hostname → public
            "http://8.8.8.8/v1",  # Google DNS — globally routable
            "http://1.1.1.1/v1",  # Cloudflare DNS — globally routable
        ],
    )
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
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                }
            ),
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
            json.dumps(
                {
                    "api_base_url": "https://api.openai.com/v1",
                    "api_key": "sk-test123",
                    "model": "gpt-4",
                }
            ),
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
            json.dumps(
                {
                    "api_base_url": "https://api.openai.com/v1",
                    "api_key": "key",
                    "model": "",
                }
            ),
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
            json.dumps(
                {
                    "api_base_url": "http://lmac:1234/v1",
                    "api_key": "",
                    "model": "gemma",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        with patch("src.services.llm_service._build_http_client") as mock_build:
            mock_build.return_value = MagicMock(spec=__import__("httpx").AsyncClient)
            llm = LLMService()
            llm._ensure_client()
            mock_build.assert_called_once_with("http://lmac:1234/v1", 300.0)

    def test_public_url_uses_system_proxy(self, tmp_path, monkeypatch):
        """Public base_url should use the default httpx client (system proxy)."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "https://api.openai.com/v1",
                    "api_key": "sk-abc",
                    "model": "gpt-4",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        with patch("src.services.llm_service._build_http_client") as mock_build:
            mock_build.return_value = MagicMock(spec=__import__("httpx").AsyncClient)
            llm = LLMService()
            llm._ensure_client()
            mock_build.assert_called_once_with("https://api.openai.com/v1", 300.0)

    def test_custom_timeout_passed_to_http_client(self, tmp_path, monkeypatch):
        """Custom timeout in config should be forwarded to _build_http_client."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                    "timeout": 600,
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        with patch("src.services.llm_service._build_http_client") as mock_build:
            mock_build.return_value = MagicMock(spec=__import__("httpx").AsyncClient)
            llm = LLMService()
            llm._ensure_client()
            mock_build.assert_called_once_with("http://localhost:11434/v1", 600.0)

    def test_zero_timeout_means_no_timeout(self, tmp_path, monkeypatch):
        """timeout=0 in config means no timeout (passed as 0.0)."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                    "timeout": 0,
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        with patch("src.services.llm_service._build_http_client") as mock_build:
            mock_build.return_value = MagicMock(spec=__import__("httpx").AsyncClient)
            llm = LLMService()
            llm._ensure_client()
            mock_build.assert_called_once_with("http://localhost:11434/v1", 0.0)


class TestListModels:
    """Tests for list_models method."""

    @pytest.mark.asyncio
    async def test_list_models_returns_sorted_ids(self, tmp_path, monkeypatch):
        """Should return a sorted list of model IDs."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                }
            ),
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
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                }
            ),
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


class TestBuildHttpClient:
    """Tests for _build_http_client timeout behaviour."""

    def test_default_timeout_creates_timeout_object(self):
        """Default timeout (300s) should produce an httpx.Timeout with read=300."""
        import httpx

        from src.services.llm_service import _build_http_client

        client = _build_http_client("https://api.openai.com/v1", 300.0)
        assert isinstance(client.timeout, httpx.Timeout)
        assert client.timeout.read == 300.0

    def test_zero_timeout_means_none(self):
        """timeout=0 should produce httpx.Timeout(None) — no timeout at all."""
        import httpx

        from src.services.llm_service import _build_http_client

        client = _build_http_client("http://localhost:11434/v1", 0.0)
        assert isinstance(client.timeout, httpx.Timeout)
        # httpx.Timeout(None) stores None for all fields
        assert client.timeout.read is None

    def test_custom_timeout_value(self):
        """Custom timeout should be reflected in the client's timeout.read."""
        import httpx

        from src.services.llm_service import _build_http_client

        client = _build_http_client("https://api.openai.com/v1", 900.0)
        assert isinstance(client.timeout, httpx.Timeout)
        assert client.timeout.read == 900.0


class TestChatStream:
    """Tests for the streaming chat() method."""

    @pytest.mark.asyncio
    async def test_chat_collects_stream_chunks(self, tmp_path, monkeypatch):
        """chat() should collect all streamed chunks into one string."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        # Build fake ChatCompletionChunk-like objects
        def _make_chunk(text: str | None):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = text
            return chunk

        fake_chunks = [
            _make_chunk('{"status"'),
            _make_chunk(': "ok"'),
            _make_chunk("}"),
            _make_chunk(None),  # trailing None should be ignored
        ]

        # create(..., stream=True) is awaited and returns an async-iterable object
        class FakeAsyncStream:
            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                for c in fake_chunks:
                    yield c

        async def fake_create(*args, **kwargs):
            return FakeAsyncStream()

        llm = LLMService()
        llm._ensure_client()
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)
        llm.client.chat.completions.create = fake_create

        result = await llm.chat("sys", "user")
        assert result == '{"status": "ok"}'

    @pytest.mark.asyncio
    async def test_chat_returns_empty_string_when_no_content(self, tmp_path, monkeypatch):
        """chat() should return '' when all chunks have None content."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        def _make_chunk(text: str | None):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = text
            return chunk

        class FakeAsyncStream:
            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                yield _make_chunk(None)

        async def fake_create(*args, **kwargs):
            return FakeAsyncStream()

        llm = LLMService()
        llm._ensure_client()
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)
        llm.client.chat.completions.create = fake_create

        result = await llm.chat("sys", "user")
        assert result == ""

    @pytest.mark.asyncio
    async def test_chat_propagates_exception(self, tmp_path, monkeypatch):
        """chat() should re-raise exceptions raised by create()."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_base_url": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        async def broken_create(*args, **kwargs):
            raise ConnectionError("stream broken")

        llm = LLMService()
        llm._ensure_client()
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)
        llm.client.chat.completions.create = broken_create

        with pytest.raises(ConnectionError, match="stream broken"):
            await llm.chat("sys", "user")


# ---------------------------------------------------------------------------
# Anthropic provider tests
# ---------------------------------------------------------------------------


class _FakeAnthropicStream:
    """Async context manager exposing a text_stream async iterator."""

    def __init__(self, texts: list[str | None]):
        self._texts = texts

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @property
    def text_stream(self):
        async def _gen():
            for t in self._texts:
                yield t

        return _gen()


class TestAnthropicEnsureClient:
    """Tests for _ensure_client when provider=anthropic."""

    def test_anthropic_client_created(self, tmp_path, monkeypatch):
        """provider=anthropic with api_key should create an AsyncAnthropic client."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_base_url": "",
                    "api_key": "sk-ant-test",
                    "model": "claude-3-5-sonnet-latest",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        assert llm._provider == "anthropic"
        assert llm.anthropic_client is not None
        assert llm.client is None
        assert llm.model == "claude-3-5-sonnet-latest"

    def test_anthropic_raises_without_api_key(self, tmp_path, monkeypatch):
        """provider=anthropic without api_key should raise ValueError."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_base_url": "",
                    "api_key": "",
                    "model": "claude-3-5-sonnet-latest",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        with pytest.raises(ValueError, match="Anthropic"):
            llm._ensure_client()

    def test_anthropic_default_model_when_empty(self, tmp_path, monkeypatch):
        """provider=anthropic with empty model should default to claude-3-5-sonnet-latest."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_key": "sk-ant-test",
                    "model": "",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        assert llm.model == "claude-3-5-sonnet-latest"

    def test_anthropic_custom_base_url(self, tmp_path, monkeypatch):
        """provider=anthropic with custom base_url should pass it to AsyncAnthropic."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_base_url": "https://my-proxy.example.com/v1",
                    "api_key": "sk-ant-test",
                    "model": "claude-3-5-sonnet-latest",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        assert llm.anthropic_client is not None
        assert llm._base_url == "https://my-proxy.example.com/v1"


class TestAnthropicListModels:
    """Tests for list_models when provider=anthropic."""

    @pytest.mark.asyncio
    async def test_returns_sorted_ids(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_key": "sk-ant-test",
                    "model": "claude-3-5-sonnet-latest",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        m1 = MagicMock()
        m1.id = "claude-3-5-sonnet-latest"
        m2 = MagicMock()
        m2.id = "claude-3-5-haiku-latest"
        m3 = MagicMock()
        m3.id = "claude-3-opus-latest"
        mock_response = MagicMock()
        mock_response.data = [m1, m2, m3]

        llm = LLMService()
        llm._ensure_client()
        llm.anthropic_client.models.list = AsyncMock(return_value=mock_response)
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)

        result = await llm.list_models()
        assert result == [
            "claude-3-5-haiku-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-opus-latest",
        ]


class TestAnthropicChatStream:
    """Tests for the streaming chat() method with Anthropic provider."""

    @pytest.mark.asyncio
    async def test_chat_collects_text_stream(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_key": "sk-ant-test",
                    "model": "claude-3-5-sonnet-latest",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)

        fake_stream = _FakeAnthropicStream(['{"status"', ': "ok"', "}", None])

        def fake_messages_stream(**kwargs):
            return fake_stream

        llm.anthropic_client.messages.stream = fake_messages_stream

        result = await llm.chat("sys", "user")
        assert result == '{"status": "ok"}'

    @pytest.mark.asyncio
    async def test_chat_propagates_exception(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_key": "sk-ant-test",
                    "model": "claude-3-5-sonnet-latest",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)

        class BrokenStream:
            async def __aenter__(self):
                raise ConnectionError("anthropic stream broken")

            async def __aexit__(self, *a):
                return False

        def fake_messages_stream(**kwargs):
            return BrokenStream()

        llm.anthropic_client.messages.stream = fake_messages_stream

        with pytest.raises(ConnectionError, match="anthropic stream broken"):
            await llm.chat("sys", "user")


class TestAnthropicTestConnection:
    """Tests for test_connection() with Anthropic provider."""

    @pytest.mark.asyncio
    async def test_returns_text_block_content(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "provider": "anthropic",
                    "api_key": "sk-ant-test",
                    "model": "claude-3-5-sonnet-latest",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_mod, "_CONFIG_PATH", config_path)

        llm = LLMService()
        llm._ensure_client()
        monkeypatch.setattr(llm, "_ensure_client", lambda: None)

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = '{"status": "ok"}'
        mock_response = MagicMock()
        mock_response.content = [text_block]

        llm.anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        result = await llm.test_connection()
        assert result == '{"status": "ok"}'
