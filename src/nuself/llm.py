"""LLM adapters used by NuSelf agents."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from nuself.config import ConfigSystem
from nuself.config import runtime_paths
from nuself.logs import write_log_event

ChatRole: TypeAlias = Literal["system", "user", "assistant"]
JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def parse_llm_json_object(raw: str) -> dict[str, object]:
    """Parse an LLM response that should contain one JSON object.

    Tolerates Markdown code fences because weaker models sometimes
    ignore 'return JSON only' instructions.
    """
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    parsed: object = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response is not a JSON object")
    return cast(dict[str, object], parsed)


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
    def from_project(cls, project_root: Path | None = None) -> LLMSettings:
        config = ConfigSystem.load(project_root=project_root)
        endpoint = config.llm.endpoints[0]
        return cls(
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            model=endpoint.model,
            provider="anthropic" if endpoint.anthropic else "openai",
            timeout_seconds=endpoint.timeout_seconds,
        )


@dataclass(frozen=True)
class LangChainLLMEndpoint:
    """One configured LangChain chat model endpoint."""

    index: int
    settings: LLMSettings
    model: BaseChatModel


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


# ============================================================================
# LangChain-backed default LLM with endpoint failover
# ============================================================================


def default_llm(project_root: Path | None = None) -> ChatLLM:
    """Return the configured LLM, or a deterministic local fallback."""
    langchain_endpoints = configured_langchain_chat_models(project_root)
    if not langchain_endpoints:
        return LocalFallbackLLM()
    return _LangChainFailoverLLM(langchain_endpoints, project_root=project_root)


class _LangChainFailoverLLM:
    """LangChain-backed LLM with ordered endpoint failover.

    Wraps ``configured_langchain_chat_models`` so that background agents
    (curator, optimizer, intake, etc.) get failover without importing
    LangChain model classes directly.
    """

    def __init__(
        self,
        endpoints: tuple[LangChainLLMEndpoint, ...],
        *,
        project_root: Path | None = None,
    ) -> None:
        self._endpoints = endpoints
        self._project_root = project_root
        self._start_index = _load_llm_state(project_root)

    def complete(self, messages: list[ChatMessage]) -> str:
        last_error: RuntimeError | None = None
        for endpoint in self._ordered_endpoints():
            try:
                result = _invoke_langchain_model(endpoint.model, messages)
            except RuntimeError as exc:
                last_error = exc
                if not is_endpoint_availability_error(str(exc)):
                    raise
                self._log_failover(exc, endpoint)
                continue
            _save_llm_state(self._project_root, endpoint.index)
            return result
        if last_error is not None:
            raise RuntimeError(f"all configured LLM endpoints failed: {redact_llm_error(str(last_error))}") from last_error
        raise RuntimeError("LLM API key is not configured")

    def _ordered_endpoints(self) -> tuple[LangChainLLMEndpoint, ...]:
        start = self._start_index
        by_index = {ep.index: ep for ep in self._endpoints}
        ordered: list[LangChainLLMEndpoint] = []
        if start in by_index:
            ordered.append(by_index[start])
        ordered.extend(ep for ep in self._endpoints if ep.index not in {ep.index for ep in ordered})
        return tuple(ordered)

    def _log_failover(self, exc: RuntimeError, failed: LangChainLLMEndpoint) -> None:
        remaining = [ep for ep in self._ordered_endpoints() if ep.index != failed.index]
        event = "llm_endpoint_failed_over" if remaining else "llm_endpoint_unavailable"
        status = "failed_over" if remaining else "exhausted"
        message = "LLM endpoint failed; trying next configured endpoint" if remaining else (
            "LLM endpoint failed and no fallback endpoint remains"
        )
        metadata: dict[str, object] = {
            "endpoint_index": failed.index,
            "base_url": failed.settings.base_url,
            "model": failed.settings.model,
        }
        if remaining:
            metadata["next_endpoint_index"] = remaining[0].index
        write_log_event(
            "chat",
            event,
            message,
            project_root=self._project_root,
            status=status,
            error=redact_llm_error(str(exc)),
            metadata=metadata,
        )


def _invoke_langchain_model(model: BaseChatModel, messages: list[ChatMessage]) -> str:
    """Invoke a LangChain chat model with NuSelf messages, return text."""
    lc_messages: list[SystemMessage | HumanMessage] = []
    for m in messages:
        if m.role == "system":
            lc_messages.append(SystemMessage(content=m.content))
        else:
            lc_messages.append(HumanMessage(content=m.content))
    try:
        result = model.invoke(lc_messages)
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    content: object = result.content  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    if isinstance(content, str):
        return content
    return str(cast(Any, content))


# ============================================================================
# LangChain model factories and helpers
# ============================================================================


def configured_langchain_chat_models(project_root: Path | None = None) -> tuple[LangChainLLMEndpoint, ...]:
    """Return configured LangChain chat models in failover order with stateful start."""
    endpoints = _configured_llm_endpoints(project_root)
    if not endpoints:
        return ()
    start_index = _load_llm_state(project_root)
    by_index = {ep.index: ep for ep in endpoints}
    ordered: list[LangChainLLMEndpoint] = []
    if start_index in by_index:
        ordered.append(by_index[start_index])
    ordered.extend(ep for ep in endpoints if ep.index not in {ep.index for ep in ordered})
    return tuple(ordered)


def _configured_llm_endpoints(project_root: Path | None = None) -> tuple[LangChainLLMEndpoint, ...]:
    """Return LangChain endpoint wrappers from config (no stateful ordering)."""
    config = ConfigSystem.load(project_root=project_root)
    result: list[LangChainLLMEndpoint] = []
    for index, ep_cfg in enumerate(config.llm.endpoints):
        if ep_cfg.api_key.strip() == "":
            continue
        settings = LLMSettings(
            base_url=ep_cfg.base_url,
            api_key=ep_cfg.api_key,
            model=ep_cfg.model,
            provider="anthropic" if ep_cfg.anthropic else "openai",
            timeout_seconds=ep_cfg.timeout_seconds,
        )
        model = _endpoint_langchain_chat_model(settings)
        result.append(LangChainLLMEndpoint(index=index, settings=settings, model=model))
    return tuple(result)


def _endpoint_langchain_chat_model(settings: LLMSettings) -> BaseChatModel:
    model_args: dict[str, object] = {
        "api_key": settings.api_key,
        "timeout": settings.timeout_seconds,
        "max_retries": 0,
        "temperature": 0.1,
    }
    if settings.provider == "anthropic":
        anthropic_model = cast(Any, ChatAnthropic)
        return cast(BaseChatModel, anthropic_model(
            model_name=settings.model,
            base_url=settings.base_url,
            **model_args,
        ))
    openai_model = cast(Any, ChatOpenAI)
    return cast(BaseChatModel, openai_model(
        model=settings.model,
        base_url=settings.base_url,
        **model_args,
    ))


# ============================================================================
# Public helpers (used by chat.py, persona.py for per-call failover)
# ============================================================================


def record_llm_endpoint_success(project_root: Path | None, endpoint_index: int) -> None:
    """Remember the last successful configured LLM endpoint."""
    _save_llm_state(project_root, endpoint_index)


HTTP_AVAILABILITY_STATUS_RE = __import__("re").compile(r"\bhttp\s+(401|402|403|429)\b", __import__("re").IGNORECASE)
"""Regex matching HTTP availability status codes in error messages."""


def is_endpoint_availability_error(message: str) -> bool:
    """Return whether an LLM error should trigger endpoint failover."""
    if HTTP_AVAILABILITY_STATUS_RE.search(message):
        return True
    lowered = message.lower()
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


def redact_llm_error(message: str) -> str:
    """Redact and truncate an LLM error for logs."""
    if len(message) <= 500:
        return message
    return message[:497] + "..."


# ============================================================================
# Persistent state: remember last working endpoint index
# ============================================================================


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
