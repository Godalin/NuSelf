"""LLM adapters used by NuSelf agents."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Literal, cast

from anthropic import (
    APIConnectionError as AnthropicAPIConnectionError,
    APITimeoutError as AnthropicAPITimeoutError,
    AuthenticationError as AnthropicAuthenticationError,
    PermissionDeniedError as AnthropicPermissionDeniedError,
    RateLimitError as AnthropicRateLimitError,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError as OpenAIAPIConnectionError,
    APITimeoutError as OpenAIAPITimeoutError,
    AuthenticationError as OpenAIAuthenticationError,
    PermissionDeniedError as OpenAIPermissionDeniedError,
    RateLimitError as OpenAIRateLimitError,
)

from nuself.config import ConfigSystem, SystemConfig
from nuself.config import runtime_paths
from nuself.runtime.diagnostics import (
    redact_sensitive_text,
    safe_exception_message,
)
from nuself.runtime.observability import (
    report_corrupt_record,
)
from nuself.storage import write_json_atomic

@dataclass(frozen=True)
class LLMSettings:
    """Configured model endpoint settings."""

    base_url: str
    api_key: str = field(repr=False)
    model: str
    provider: Literal["openai", "anthropic"] = "openai"
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class LangChainLLMEndpoint:
    """One configured LangChain chat model endpoint."""

    index: int
    settings: LLMSettings
    model: BaseChatModel


# ============================================================================
# LangChain model factories and helpers
# ============================================================================


def configured_langchain_chat_models(
    project_root: Path | None = None,
    *,
    config: SystemConfig | None = None,
) -> tuple[LangChainLLMEndpoint, ...]:
    """Return configured LangChain chat models in failover order with stateful start."""
    endpoints = _configured_llm_endpoints(project_root, config=config)
    if not endpoints:
        return ()
    start_index = _load_llm_state(
        project_root,
        available_indices={endpoint.index for endpoint in endpoints},
    )
    by_index = {ep.index: ep for ep in endpoints}
    ordered: list[LangChainLLMEndpoint] = []
    if start_index in by_index:
        ordered.append(by_index[start_index])
    ordered.extend(ep for ep in endpoints if ep.index not in {ep.index for ep in ordered})
    return tuple(ordered)


def _configured_llm_endpoints(
    project_root: Path | None = None,
    *,
    config: SystemConfig | None = None,
) -> tuple[LangChainLLMEndpoint, ...]:
    """Return LangChain endpoint wrappers from config (no stateful ordering)."""
    effective = config or ConfigSystem.load(project_root=project_root)
    result: list[LangChainLLMEndpoint] = []
    for index, ep_cfg in enumerate(effective.llm.endpoints):
        if ep_cfg.api_key.strip() == "":
            continue
        settings = LLMSettings(
            base_url=ep_cfg.base_url,
            api_key=ep_cfg.api_key,
            model=ep_cfg.model,
            provider="anthropic" if ep_cfg.anthropic else "openai",
            timeout_seconds=ep_cfg.timeout_seconds,
        )
        result.append(build_langchain_endpoint(index, settings))
    return tuple(result)


def build_langchain_endpoint(
    index: int,
    settings: LLMSettings,
) -> LangChainLLMEndpoint:
    """Build one typed endpoint through the production provider adapters."""

    if index < 0:
        raise ValueError("LLM endpoint index must be non-negative")
    return LangChainLLMEndpoint(
        index=index,
        settings=settings,
        model=_langchain_chat_model(settings),
    )


def _langchain_chat_model(settings: LLMSettings) -> BaseChatModel:
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
            base_url=_anthropic_sdk_base_url(settings.base_url),
            thinking={"type": "disabled"},
            **model_args,
        ))
    openai_model = cast(Any, ChatOpenAI)
    return cast(BaseChatModel, openai_model(
        model=settings.model,
        base_url=settings.base_url,
        **model_args,
    ))


def _anthropic_sdk_base_url(base_url: str) -> str:
    """Return the API root expected by an SDK that appends ``/v1/messages``."""

    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized[:-3]
    return normalized


# ============================================================================
# Public helpers (used by chat.py, persona.py for per-call failover)
# ============================================================================


def record_llm_endpoint_success(project_root: Path | None, endpoint_index: int) -> None:
    """Remember the last successful configured LLM endpoint."""
    from nuself.agent.chat.audit import run_chat_observed

    run_chat_observed(
        lambda: _save_llm_state(project_root, endpoint_index),
        event="llm_endpoint_state_write_failed",
        project_root=project_root,
        metadata={"endpoint_index": endpoint_index},
    )


_ENDPOINT_AVAILABILITY_ERRORS = (
    AnthropicAPIConnectionError,
    AnthropicAPITimeoutError,
    AnthropicAuthenticationError,
    AnthropicPermissionDeniedError,
    AnthropicRateLimitError,
    OpenAIAPIConnectionError,
    OpenAIAPITimeoutError,
    OpenAIAuthenticationError,
    OpenAIPermissionDeniedError,
    OpenAIRateLimitError,
    ConnectionError,
    TimeoutError,
)
_ENDPOINT_AVAILABILITY_STATUS_CODES = frozenset(
    {401, 402, 403, 408, 429, 500, 502, 503, 504}
)


def is_endpoint_availability_error(error: BaseException) -> bool:
    """Classify provider availability without inspecting exception text."""

    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _ENDPOINT_AVAILABILITY_ERRORS):
            return True
        status_code = getattr(current, "status_code", None)
        if (
            type(status_code) is int
            and status_code in _ENDPOINT_AVAILABILITY_STATUS_CODES
        ):
            return True
        response = getattr(current, "response", None)
        response_status = getattr(response, "status_code", None)
        if (
            type(response_status) is int
            and response_status in _ENDPOINT_AVAILABILITY_STATUS_CODES
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def redact_llm_error(message: str | BaseException) -> str:
    """Redact and truncate an LLM error for logs."""
    text = (
        message
        if isinstance(message, str)
        else safe_exception_message(message)
    )
    redacted = redact_sensitive_text(text)
    if len(redacted) <= 500:
        return redacted
    return redacted[:497] + "..."


def redacted_llm_diagnostic(error: BaseException) -> RuntimeError:
    """Project a provider failure without retaining its sensitive context."""

    diagnostic = RuntimeError(redact_llm_error(error))
    diagnostic.__suppress_context__ = True
    return diagnostic


# ============================================================================
# Persistent state: remember last working endpoint index
# ============================================================================


@dataclass(frozen=True)
class LLMEndpointState:
    """Versioned derived preference for the last successful endpoint."""

    schema_version: int
    active_endpoint_index: int

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("LLM endpoint state version is unsupported")
        if (
            type(self.active_endpoint_index) is not int
            or self.active_endpoint_index < 0
        ):
            raise ValueError(
                "LLM endpoint state index must be a non-negative integer"
            )

    @classmethod
    def from_wire(cls, raw: object) -> LLMEndpointState:
        if not isinstance(raw, dict):
            raise ValueError("LLM endpoint state must be a JSON object")
        data = cast(dict[object, object], raw)
        if set(data) != {"schema_version", "active_endpoint_index"}:
            raise ValueError("LLM endpoint state fields are invalid")
        schema_version = data["schema_version"]
        endpoint_index = data["active_endpoint_index"]
        if type(schema_version) is not int:
            raise ValueError("LLM endpoint state version must be an integer")
        if type(endpoint_index) is not int:
            raise ValueError("LLM endpoint state index must be an integer")
        return cls(
            schema_version=schema_version,
            active_endpoint_index=endpoint_index,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "active_endpoint_index": self.active_endpoint_index,
        }


def _load_llm_state(
    project_root: Path | None,
    *,
    available_indices: set[int] | None = None,
) -> int | None:
    path = runtime_paths(project_root).runtime_dir / "llm_state.json"
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        state = LLMEndpointState.from_wire(raw)
        if (
            available_indices is not None
            and state.active_endpoint_index not in available_indices
        ):
            raise ValueError(
                "saved LLM endpoint index is not currently configured"
            )
        return state.active_endpoint_index
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, ValueError):
        report_corrupt_record(
            ValueError("LLM endpoint preference state is invalid"),
            component="chat",
            collection="llm_endpoint_state",
            record_id=path.stem,
            project_root=project_root,
        )
        return None


def _save_llm_state(project_root: Path | None, endpoint_index: int) -> None:
    state = LLMEndpointState(
        schema_version=1,
        active_endpoint_index=endpoint_index,
    )
    path = runtime_paths(project_root).runtime_dir / "llm_state.json"
    write_json_atomic(path, state.to_wire())
