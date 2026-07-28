"""LLM adapters used by NuSelf agents."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from nuself.config import ConfigSystem
from nuself.config import runtime_paths
from nuself.runtime.observability import (
    report_corrupt_record,
    run_observed_best_effort,
)
from nuself.storage import write_json_atomic

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


# ============================================================================
# LangChain model factories and helpers
# ============================================================================


def configured_langchain_chat_models(project_root: Path | None = None) -> tuple[LangChainLLMEndpoint, ...]:
    """Return configured LangChain chat models in failover order with stateful start."""
    endpoints = _configured_llm_endpoints(project_root)
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
    run_observed_best_effort(
        lambda: _save_llm_state(project_root, endpoint_index),
        component="chat",
        event="llm_endpoint_state_write_failed",
        message="Could not persist the last successful LLM endpoint",
        project_root=project_root,
        metadata={"endpoint_index": endpoint_index},
    )


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
