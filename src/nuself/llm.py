"""LLM adapters used by NuSelf agents."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Literal, Protocol, TypeAlias, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nuself.config_system import ConfigSystem
from nuself.config import runtime_paths
from nuself.logs import write_log_event

ChatRole: TypeAlias = Literal["system", "user", "assistant"]
JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
HTTP_AVAILABILITY_STATUS_RE = re.compile(r"\bhttp\s+(401|402|403|429)\b", re.IGNORECASE)


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
    """Configured model endpoint settings."""

    base_url: str
    api_key: str
    model: str
    provider: Literal["openai", "anthropic"] = "openai"
    timeout_seconds: float = 60.0

    @classmethod
    def from_project(cls, project_root: Path | None = None) -> "LLMSettings":
        endpoints = configured_llm_endpoints(project_root)
        if endpoints:
            return endpoints[0].settings
        config = ConfigSystem.load(project_root=project_root)
        endpoint = config.llm.endpoints[0]
        return cls(
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            model=endpoint.model,
            provider="anthropic" if endpoint.anthropic else "openai",
        )


@dataclass(frozen=True)
class LLMEndpoint:
    """One configured LLM endpoint."""

    index: int
    settings: LLMSettings


class OpenAICompatibleLLM:
    """Small standard-library client for OpenAI-compatible chat completions."""

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings

    def complete(self, messages: list[ChatMessage]) -> str:
        if self._settings.api_key.strip() == "":
            raise RuntimeError("LLM API key is not configured")
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
                "User-Agent": "NuSelf/0.1.0",
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


class AnthropicLLM:
    """Small standard-library client for Anthropic Messages API."""

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings

    def complete(self, messages: list[ChatMessage]) -> str:
        if self._settings.api_key.strip() == "":
            raise RuntimeError("LLM API key is not configured")
        payload: dict[str, JsonValue] = {
            "model": self._settings.model,
            "messages": _anthropic_messages(messages),
            "max_tokens": 4096,
        }
        system_prompt = _anthropic_system_prompt(messages)
        if system_prompt:
            payload["system"] = system_prompt
        request = Request(
            f"{self._settings.base_url.rstrip('/')}/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self._settings.api_key,
                "anthropic-version": "2023-06-01",
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
        return _extract_anthropic_text(body)


class FailoverLLM:
    """OpenAI-compatible LLM with ordered endpoint failover."""

    def __init__(self, endpoints: tuple[LLMEndpoint, ...], *, project_root: Path | None = None) -> None:
        self._endpoints = endpoints
        self._project_root = project_root

    def complete(self, messages: list[ChatMessage]) -> str:
        if not self._endpoints:
            raise RuntimeError("LLM API key is not configured")
        last_error: RuntimeError | None = None
        ordered_endpoints = self._ordered_endpoints()
        for position, endpoint in enumerate(ordered_endpoints):
            try:
                result = _endpoint_llm(endpoint.settings).complete(messages)
            except RuntimeError as exc:
                last_error = exc
                if _is_endpoint_availability_error(str(exc)):
                    remaining = ordered_endpoints[position + 1 :]
                    event = "llm_endpoint_failed_over" if remaining else "llm_endpoint_unavailable"
                    status = "failed_over" if remaining else "exhausted"
                    message = "LLM endpoint failed; trying next configured endpoint" if remaining else (
                        "LLM endpoint failed and no fallback endpoint remains"
                    )
                    metadata: dict[str, object] = {
                        "endpoint_index": endpoint.index,
                        "base_url": endpoint.settings.base_url,
                        "model": endpoint.settings.model,
                    }
                    if remaining:
                        metadata["next_endpoint_index"] = remaining[0].index
                    write_log_event(
                        "chat",
                        event,
                        message,
                        project_root=self._project_root,
                        status=status,
                        error=_redact_llm_error(str(exc)),
                        metadata=metadata,
                    )
                    continue
                raise
            _save_llm_state(self._project_root, endpoint.index)
            return result
        if last_error is not None:
            raise RuntimeError(f"all configured LLM endpoints failed: {_redact_llm_error(str(last_error))}") from last_error
        raise RuntimeError("LLM API key is not configured")

    def _ordered_endpoints(self) -> tuple[LLMEndpoint, ...]:
        start_index = _load_llm_state(self._project_root)
        by_index = {endpoint.index: endpoint for endpoint in self._endpoints}
        ordered_indices = [start_index] if start_index in by_index else []
        ordered_indices.extend(endpoint.index for endpoint in self._endpoints if endpoint.index not in ordered_indices)
        return tuple(by_index[index] for index in ordered_indices)


class LocalFallbackLLM:
    """Deterministic local fallback when no API key is configured."""

    def complete(self, messages: list[ChatMessage]) -> str:
        if messages and "Compress a private NuSelf conversation" in messages[0].content:
            raise RuntimeError("LLM API key is not configured")
        last_user = ""
        for message in reversed(messages):
            if message.role == "user":
                last_user = message.content
                break
        return (
            "LLM API is not configured yet. I saved the message and can use local memory/context, "
            f"but real reasoning needs an API key. Last message: {last_user}"
        )


def default_llm(project_root: Path | None = None) -> ChatLLM:
    """Return the configured LLM, or a deterministic local fallback."""

    endpoints = configured_llm_endpoints(project_root)
    if not endpoints:
        return LocalFallbackLLM()
    return FailoverLLM(endpoints, project_root=project_root)


def configured_llm_endpoints(project_root: Path | None = None) -> tuple[LLMEndpoint, ...]:
    config = ConfigSystem.load(project_root=project_root)
    endpoints: list[LLMEndpoint] = []
    for index, endpoint_config in enumerate(config.llm.endpoints):
        settings = LLMSettings(
            base_url=endpoint_config.base_url,
            api_key=endpoint_config.api_key,
            model=endpoint_config.model,
            provider="anthropic" if endpoint_config.anthropic else "openai",
            timeout_seconds=endpoint_config.timeout_seconds,
        )
        if settings.api_key.strip() != "":
            endpoints.append(LLMEndpoint(index=index, settings=settings))
    return tuple(endpoints)


def _load_llm_state(project_root: Path | None) -> int:
    path = runtime_paths(project_root).runtime_dir / "llm_state.json"
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(raw, dict):
        return 0
    data = cast(dict[object, object], raw)
    index = data.get("active_endpoint_index")
    return index if isinstance(index, int) and index >= 0 else 0


def _save_llm_state(project_root: Path | None, endpoint_index: int) -> None:
    paths = runtime_paths(project_root)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    path = paths.runtime_dir / "llm_state.json"
    payload: dict[str, JsonValue] = {"active_endpoint_index": endpoint_index}
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def _is_endpoint_availability_error(message: str) -> bool:
    lowered = message.lower()
    if HTTP_AVAILABILITY_STATUS_RE.search(message):
        return True
    indicators = (
        "invalidsubscription",
        "subscription",
        "quota",
        "billing",
        "credit",
        "insufficient",
        "balance",
        "rate limit",
        "too many requests",
    )
    return any(indicator in lowered for indicator in indicators)


def _redact_llm_error(message: str) -> str:
    if len(message) <= 500:
        return message
    return message[:497] + "..."


def _endpoint_llm(settings: LLMSettings) -> ChatLLM:
    if settings.provider == "anthropic":
        return AnthropicLLM(settings)
    return OpenAICompatibleLLM(settings)


def _anthropic_system_prompt(messages: list[ChatMessage]) -> str:
    return "\n\n".join(message.content for message in messages if message.role == "system")


def _anthropic_messages(messages: list[ChatMessage]) -> list[JsonValue]:
    converted: list[JsonValue] = [
        {"role": message.role, "content": message.content}
        for message in messages
        if message.role in {"user", "assistant"}
    ]
    if converted:
        return converted
    return [{"role": "user", "content": ""}]


def _extract_anthropic_text(body: str) -> str:
    raw: object = json.loads(body)
    if not isinstance(raw, dict):
        raise RuntimeError("Anthropic response must be a JSON object")
    raw_object = cast(dict[str, object], raw)
    content = raw_object.get("content")
    if not isinstance(content, list):
        raise RuntimeError("Anthropic response did not include content")
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
    raise RuntimeError("Anthropic response did not include text content")


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
