"""LLM Service — supports OpenAI-compatible and Anthropic APIs for AI deduction.

Wraps AsyncOpenAI / AsyncAnthropic for chat completion requests.

Proxy note:
  httpx (used by both SDKs) inherits the system's HTTP_PROXY /
  HTTPS_PROXY env-vars automatically.  For servers running on a local /
  private network (LM Studio, Ollama, …) the traffic must NOT go through a
  corporate proxy, so we inject a no-proxy transport when the configured
  base_url is detected as a private/loopback address.  Public endpoints
  (api.openai.com, api.anthropic.com, etc.) continue to use the system
  proxy as normal.
"""

import ipaddress
from urllib.parse import urlparse

import anthropic
import httpx
from anthropic import AsyncAnthropic
from loguru import logger
from openai import AsyncOpenAI

from src.services.config import load_config

# ---------------------------------------------------------------------------
# Private / loopback address detection
# ---------------------------------------------------------------------------

_PRIVATE_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "::1",  # bare IPv6 loopback (after urlparse strips brackets from [::1])
}


def _is_local_url(url: str) -> bool:
    """Return True if *url* resolves to a loopback or RFC-1918 private address.

    Covers:
    - loopback:  127.x.x.x / ::1 / "localhost"
    - link-local: 169.254.x.x / fe80::/10
    - RFC-1918:  10.x / 172.16-31.x / 192.168.x
    - Unique-local IPv6: fc00::/7
    - Plain hostnames without dots (e.g. "lmac", "my-server") — these are
      almost always intranet names that won't be reachable through a proxy.
    """
    if not url:
        return False
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False

    host = host.lower()

    if host in _PRIVATE_HOSTNAMES:
        return True

    # Plain hostname with no dots → likely an intranet name
    if host and "." not in host and ":" not in host:
        return True

    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback or addr.is_private or addr.is_link_local
    except ValueError:
        pass  # Not a bare IP address — it's a hostname like "lmac" or "api.openai.com"

    return False


# ---------------------------------------------------------------------------
# Transport factory
# ---------------------------------------------------------------------------


def _build_http_client(base_url: str, timeout: float = 300.0) -> httpx.AsyncClient:
    """Return an AsyncClient that bypasses the proxy for local URLs.

    Args:
        base_url: The API base URL used to determine proxy settings.
        timeout: Request timeout in seconds. 0 means no timeout.
    """
    # httpx.Timeout(None) means no timeout; otherwise set read/connect timeouts.
    httpx_timeout = (
        httpx.Timeout(None)
        if timeout == 0
        else httpx.Timeout(
            connect=10.0,
            read=float(timeout),
            write=float(timeout),
            pool=10.0,
        )
    )
    if _is_local_url(base_url):
        logger.debug(
            "_build_http_client: local URL detected — bypassing system proxy (timeout={}s)",
            "∞" if timeout == 0 else timeout,
        )
        return httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(),  # no proxy
            timeout=httpx_timeout,
        )
    logger.debug(
        "_build_http_client: public URL detected — using system proxy (timeout={}s)",
        "∞" if timeout == 0 else timeout,
    )
    return httpx.AsyncClient(timeout=httpx_timeout)  # httpx default: honours env proxy vars


class LLMService:
    """Manages connection to an OpenAI-compatible or Anthropic API for AI reasoning."""

    def __init__(self):
        self.client: AsyncOpenAI | None = None
        self.anthropic_client: AsyncAnthropic | None = None
        self.model: str = "gpt-4"
        self._provider: str = "openai"
        self._base_url: str = ""
        self._api_key: str = "no-key"
        self._timeout: float = 300.0

    def _ensure_client(self) -> None:
        """Initialize or refresh the client from current config."""
        config = load_config()
        provider = (config.get("provider") or "openai").strip().lower()
        base_url = config.get("api_base_url", "")
        model = config.get("model") or (
            "claude-3-5-sonnet-latest" if provider == "anthropic" else "gpt-4"
        )
        api_key = config.get("api_key") or "no-key"
        timeout_raw = config.get("timeout")
        # Treat None/missing as default 300; allow explicit 0 to mean "no timeout"
        timeout = float(timeout_raw) if timeout_raw is not None else 300.0
        logger.debug(
            "LLMService._ensure_client: provider={!r} base_url={!r} model={!r} api_key_set={} timeout={}s",
            provider,
            base_url,
            model,
            bool(config.get("api_key")),
            "∞" if timeout == 0 else timeout,
        )

        if provider == "anthropic":
            # Anthropic: api_key required; base_url optional (defaults to api.anthropic.com)
            if not api_key or api_key == "no-key":
                raise ValueError("Anthropic API 未配置。请在设置页面填写 API Key。")
            effective_base = base_url or "https://api.anthropic.com"
            is_local = _is_local_url(effective_base)
            http_client = _build_http_client(effective_base, timeout)
            kwargs: dict = {
                "api_key": api_key,
                "http_client": http_client,
            }
            if base_url:
                kwargs["base_url"] = base_url
            self.anthropic_client = AsyncAnthropic(**kwargs)
            self.client = None
            self._provider = "anthropic"
            self._base_url = effective_base.rstrip("/")
            logger.info(
                "LLMService Anthropic client ready: base_url={!r} model={!r} local={} timeout={}s",
                effective_base,
                model,
                is_local,
                "∞" if timeout == 0 else timeout,
            )
        else:
            if not base_url:
                raise ValueError("API 未配置。请在设置页面配置 API Base URL。")
            is_local = _is_local_url(base_url)
            http_client = _build_http_client(base_url, timeout)
            self.client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
                http_client=http_client,
            )
            self.anthropic_client = None
            self._provider = "openai"
            self._base_url = base_url.rstrip("/")
            logger.info(
                "LLMService OpenAI client ready: base_url={!r} model={!r} local={} proxy_bypassed={} timeout={}s",
                base_url,
                model,
                is_local,
                is_local,
                "∞" if timeout == 0 else timeout,
            )

        self.model = model
        self._api_key = api_key
        self._timeout = timeout

    async def list_models(self) -> list[str]:
        """Fetch available model IDs from the API endpoint.

        Returns a sorted list of model ID strings.
        """
        logger.info("list_models: fetching model list …")
        self._ensure_client()
        try:
            if self._provider == "anthropic":
                assert self.anthropic_client is not None
                models = await self.anthropic_client.models.list()
                ids = sorted([m.id for m in models.data])
            else:
                assert self.client is not None
                models = await self.client.models.list()
                ids = sorted([m.id for m in models.data])
            logger.info("list_models: got {} model(s): {}", len(ids), ids)
            return ids
        except Exception:
            logger.exception("list_models: request failed")
            raise

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a streaming chat completion request and return the full content string.

        Uses stream=True so that long-running LLM responses don't hit read timeouts
        on the first chunk.  All chunks are collected and returned as one string.
        """
        logger.debug(
            "chat: provider={!r} model={!r} system_prompt_len={} user_prompt_len={} timeout={}s",
            self._provider,
            self.model,
            len(system_prompt),
            len(user_prompt),
            "∞" if self._timeout == 0 else self._timeout,
        )
        self._ensure_client()
        try:
            if self._provider == "anthropic":
                return await self._chat_anthropic(system_prompt, user_prompt)
            return await self._chat_openai(system_prompt, user_prompt)
        except Exception:
            logger.exception(
                "chat: request failed (provider={!r} model={!r})", self._provider, self.model
            )
            raise

    async def _chat_openai(self, system_prompt: str, user_prompt: str) -> str:
        assert self.client is not None
        chunks: list[str] = []
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                chunks.append(delta)
        content = "".join(chunks)
        logger.debug("chat: openai stream complete response_len={}", len(content))
        return content

    async def _chat_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        assert self.anthropic_client is not None
        chunks: list[str] = []
        async with self.anthropic_client.messages.stream(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.3,
        ) as stream:
            async for text in stream.text_stream:
                if text:
                    chunks.append(text)
        content = "".join(chunks)
        logger.debug("chat: anthropic stream complete response_len={}", len(content))
        return content

    async def test_connection(self) -> str:
        """Test the API connection with a simple request."""
        logger.info(
            "test_connection: sending probe request (provider={!r} model={!r})",
            self._provider,
            self.model,
        )
        self._ensure_client()
        try:
            if self._provider == "anthropic":
                assert self.anthropic_client is not None
                response = await self.anthropic_client.messages.create(
                    model=self.model,
                    max_tokens=50,
                    messages=[
                        {
                            "role": "user",
                            "content": 'Say \'connection ok\' in JSON: {"status": "ok"}',
                        }
                    ],
                )
                # Anthropic content is a list of content blocks; collect text blocks
                content = "".join(
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                )
            else:
                assert self.client is not None
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": 'Say \'connection ok\' in JSON: {"status": "ok"}',
                        }
                    ],
                    max_tokens=50,
                )
                content = response.choices[0].message.content or ""
            logger.info("test_connection: success — response={!r}", content)
            return content
        except Exception:
            logger.exception(
                "test_connection: failed (provider={!r} model={!r})", self._provider, self.model
            )
            raise


__all__ = ["LLMService", "_is_local_url", "_build_http_client", "anthropic"]
