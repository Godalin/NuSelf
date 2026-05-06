"""LLM adapters used by NuSelf agents."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, Protocol, TypeAlias, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nuself.config import config_value

ChatRole: TypeAlias = Literal["system", "user", "assistant"]
JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class ChatMessage:
    """One chat message sent to or returned by an LLM."""

    role: ChatRole
    content: str

    def to_wire(self) -> dict[str, JsonValue]:
        return {"role": self.role, "content": self.content}


class ChatLLM(Protocol):
    """Minimal chat-completion interface used by agents."""

    def complete(self, messages: list[ChatMessage]) -> str: ...


@dataclass(frozen=True)
class LLMSettings:
    """OpenAI-compatible model configuration."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0

    @classmethod
    def from_project(cls, project_root: Path | None = None) -> "LLMSettings":
        return cls(
            base_url=config_value("OPENAI_BASE_URL", "https://api.openai.com/v1", project_root),
            api_key=config_value("OPENAI_API_KEY", "", project_root),
            model=config_value("OPENAI_MODEL", "gpt-4.1-mini", project_root),
        )


class OpenAICompatibleLLM:
    """Small standard-library client for OpenAI-compatible chat completions."""

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings

    def complete(self, messages: list[ChatMessage]) -> str:
        if self._settings.api_key.strip() == "":
            raise RuntimeError("OPENAI_API_KEY is not configured")
        wire_messages: list[JsonValue] = [message.to_wire() for message in messages]
        payload: dict[str, JsonValue] = {
            "model": self._settings.model,
            "messages": wire_messages,
            "temperature": 0.4,
        }
        request = Request(
            f"{self._settings.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._settings.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc.reason}") from exc
        return _extract_chat_completion_text(body)


class LocalFallbackLLM:
    """Deterministic local fallback when no API key is configured."""

    def complete(self, messages: list[ChatMessage]) -> str:
        if messages and "Compress a private NuSelf conversation" in messages[0].content:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        last_user = ""
        for message in reversed(messages):
            if message.role == "user":
                last_user = message.content
                break
        return (
            "LLM API is not configured yet. I saved the message and can use local memory/context, "
            f"but real reasoning needs OPENAI_API_KEY. Last message: {last_user}"
        )


def default_llm(project_root: Path | None = None) -> ChatLLM:
    """Return the configured LLM, or a deterministic local fallback."""

    settings = LLMSettings.from_project(project_root)
    if settings.api_key.strip() == "":
        return LocalFallbackLLM()
    return OpenAICompatibleLLM(settings)


def _extract_chat_completion_text(body: str) -> str:
    raw: object = json.loads(body)
    if not isinstance(raw, dict):
        raise RuntimeError("LLM response must be a JSON object")
    raw_object = cast(dict[str, object], raw)
    choices = raw_object.get("choices")
    if not isinstance(choices, list):
        raise RuntimeError("LLM response did not include choices")
    choice_items = cast(list[object], choices)
    if len(choice_items) == 0:
        raise RuntimeError("LLM response did not include choices")
    first_choice = choice_items[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("LLM choice must be a JSON object")
    first_choice_object = cast(dict[str, object], first_choice)
    message = first_choice_object.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("LLM choice did not include a message object")
    message_object = cast(dict[str, object], message)
    content = message_object.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in cast(list[object], content):
            if not isinstance(item, dict):
                continue
            content_item = cast(dict[str, object], item)
            text = content_item.get("text")
            if content_item.get("type") == "text" and isinstance(text, str):
                parts.append(text)
        if parts:
            return "\n".join(parts)
    raise RuntimeError("LLM response did not include text content")
