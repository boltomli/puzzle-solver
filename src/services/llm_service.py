"""LLM Service — OpenAI-compatible API client for AI deduction.

Wraps AsyncOpenAI for chat completion requests with JSON output mode.
"""

import json

from openai import AsyncOpenAI

from src.services.config import load_config


class LLMService:
    """Manages connection to an OpenAI-compatible API for AI reasoning."""

    def __init__(self):
        self.client: AsyncOpenAI | None = None
        self.model: str = "gpt-4"

    def _ensure_client(self) -> None:
        """Initialize or refresh the client from current config."""
        config = load_config()
        if not config.get("api_base_url"):
            raise ValueError("API 未配置。请在设置页面配置 API Base URL。")
        self.client = AsyncOpenAI(
            base_url=config["api_base_url"],
            api_key=config.get("api_key") or "no-key",
        )
        self.model = config.get("model") or "gpt-4"

    async def list_models(self) -> list[str]:
        """Fetch available model IDs from the API endpoint.

        Returns a sorted list of model ID strings.
        """
        self._ensure_client()
        assert self.client is not None
        models = await self.client.models.list()
        return sorted([m.id for m in models.data])

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the content string.

        Requests JSON output mode for structured responses.
        """
        self._ensure_client()
        assert self.client is not None
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,  # Lower for more deterministic reasoning
        )
        return response.choices[0].message.content or ""

    async def test_connection(self) -> str:
        """Test the API connection with a simple request.

        Returns the model's response content.
        """
        self._ensure_client()
        assert self.client is not None
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": "Say 'connection ok' in JSON: {\"status\": \"ok\"}"}
            ],
            max_tokens=50,
        )
        return response.choices[0].message.content or ""
