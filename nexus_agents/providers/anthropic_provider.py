"""AnthropicProvider - LLMProvider implementation using the Anthropic SDK."""

from __future__ import annotations

from typing import Any


class AnthropicProvider:
    """LLM provider backed by the Anthropic Messages API.

    Usage::

        provider = AnthropicProvider(api_key="sk-...")
        response = provider.chat(
            messages=[{"role": "user", "content": "Hello"}],
            model="claude-sonnet-4-20250514",
        )
    """

    def __init__(self, api_key: str | None = None, **client_kwargs: Any) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicProvider. "
                "Install it with: pip install anthropic"
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key, **client_kwargs)

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Call the Anthropic Messages API and return a normalized response."""
        kwargs: dict[str, Any] = {
            "model": model or "claude-sonnet-4-20250514",
            "messages": messages,
            "max_tokens": max_tokens or 4096,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self._client.messages.create(**kwargs)

        # Normalize content blocks
        content: Any
        if hasattr(response, "content") and isinstance(response.content, list):
            content = []
            for block in response.content:
                if hasattr(block, "type"):
                    if block.type == "text":
                        content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                    else:
                        content.append({"type": block.type})
        else:
            content = str(response.content) if hasattr(response, "content") else ""

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
            }

        return {
            "content": content,
            "stop_reason": getattr(response, "stop_reason", "end_turn"),
            "model": getattr(response, "model", model),
            "usage": usage,
        }
