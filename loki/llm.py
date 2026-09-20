"""Thin OpenAI-compatible chat-completions client.

All LLM traffic in Loki goes through this single module, which makes it
easy to audit and trivial to mock in tests. API keys are never logged.
"""

from __future__ import annotations

import httpx


class LLMError(RuntimeError):
    """Raised when a chat-completions request fails or looks wrong."""


class LLMClient:
    """Minimal client for any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if not model:
            raise ValueError("model must not be empty")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"LLMClient(model={self.model!r}, base_url={self.base_url!r}, api_key='***')"

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        """Send chat messages and return the assistant's text content."""
        url = f"{self.base_url}/chat/completions"
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model, "messages": messages, "temperature": temperature},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # The key travels in headers only, so it can't leak into this message.
            raise LLMError(f"LLM request to {self.base_url} failed: {type(exc).__name__}") from exc
        try:
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {exc}") from exc
