"""Closed schemas for direct Chat and interactive-client audit events."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _exact,
)
from nuself.runtime.audit.catalog import AuditCatalog

type ChatAuditEvent = Literal[
    "daemon_chat_completed",
    "daemon_chat_failed",
    "one_shot_chat_completed",
    "one_shot_chat_failed",
    "final_response_completed",
    "llm_endpoint_retry",
    "llm_retry_suppressed_after_tool_call",
    "llm_endpoints_exhausted",
    "llm_endpoint_state_write_failed",
    "compression_fallback",
    "interactive_history_load_failed",
    "interactive_history_write_failed",
    "completion_load_failed",
    "interactive_prompt_failed",
    "turn_retry",
    "activity_transport_degraded",
    "interactive_send_failed",
    "interactive_cleanup_failed",
]

def _string(metadata: Mapping[str, object], field: str) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise AuditSchemaError(f"audit metadata {field!r} must be non-empty")
    return value


def _bool(metadata: Mapping[str, object], field: str) -> None:
    if type(metadata[field]) is not bool:
        raise AuditSchemaError(f"audit metadata {field!r} must be a boolean")


def _non_negative_int(metadata: Mapping[str, object], field: str) -> int:
    value = metadata[field]
    if type(value) is not int or value < 0:
        raise AuditSchemaError(
            f"audit metadata {field!r} must be a non-negative integer"
        )
    return value


def _endpoint(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"endpoint_index", "model"}))
    _non_negative_int(metadata, "endpoint_index")
    _string(metadata, "model")


def _endpoint_index(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"endpoint_index"}))
    _non_negative_int(metadata, "endpoint_index")


def _final_response(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"epistemic_status"}))
    _string(metadata, "epistemic_status")


def _conversation(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"conversation_id"}))
    _string(metadata, "conversation_id")


def _completion(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"completion"}))
    if _string(metadata, "completion") not in {
        "conversations",
        "archived_conversations",
    }:
        raise AuditSchemaError("audit metadata 'completion' is invalid")


def _prompt(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"fallback"}))
    if _string(metadata, "fallback") != "builtin_input":
        raise AuditSchemaError("audit metadata 'fallback' is invalid")


def _turn_retry(metadata: Mapping[str, object]) -> None:
    _exact(
        metadata,
        frozenset(
            {
                "attempt",
                "max_attempts",
                "failure_phase",
                "request_may_have_completed",
            }
        ),
    )
    attempt = _non_negative_int(metadata, "attempt")
    maximum = _non_negative_int(metadata, "max_attempts")
    if attempt < 2 or maximum < attempt:
        raise AuditSchemaError("audit retry attempt bounds are invalid")
    _string(metadata, "failure_phase")
    _bool(metadata, "request_may_have_completed")


def _activity(metadata: Mapping[str, object]) -> None:
    base = {"stage", "error_kind", "has_subscription"}
    kind = metadata.get("error_kind")
    expected = (
        base
        | {"failure_phase", "retryable", "request_may_have_completed"}
        if kind == "connection"
        else base
    )
    _exact(metadata, frozenset(expected))
    if _string(metadata, "stage") not in {"open", "poll", "drain", "close"}:
        raise AuditSchemaError("audit metadata 'stage' is invalid")
    if _string(metadata, "error_kind") not in {"connection", "application"}:
        raise AuditSchemaError("audit metadata 'error_kind' is invalid")
    _bool(metadata, "has_subscription")
    if kind == "connection":
        _string(metadata, "failure_phase")
        _bool(metadata, "retryable")
        _bool(metadata, "request_may_have_completed")


def _cleanup(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"steps", "primary_failed"}))
    steps = metadata["steps"]
    if (
        not isinstance(steps, list)
        or not steps
        or any(
            not isinstance(step, str) or not step
            for step in cast(list[object], steps)
        )
    ):
        raise AuditSchemaError(
            "audit metadata 'steps' must be a non-empty string list"
        )
    _bool(metadata, "primary_failed")


def _definitions() -> tuple[AuditEventDefinition, ...]:
    definitions = (
        AuditEventDefinition("chat", "daemon_chat_completed", "info", "ok"),
        AuditEventDefinition(
            "chat", "daemon_chat_failed", "error", "error",
            error_policy="required",
        ),
        AuditEventDefinition("chat", "one_shot_chat_completed", "info", "ok"),
        AuditEventDefinition(
            "chat", "one_shot_chat_failed", "error", "error",
            error_policy="required",
        ),
        AuditEventDefinition(
            "chat", "final_response_completed", "info", "completed",
            metadata_validator=_final_response,
        ),
        AuditEventDefinition(
            "chat", "llm_endpoint_retry", "warning", "retry",
            error_policy="required", metadata_validator=_endpoint,
        ),
        AuditEventDefinition(
            "chat", "llm_retry_suppressed_after_tool_call", "warning",
            "fallback", error_policy="required", metadata_validator=_endpoint,
        ),
        AuditEventDefinition(
            "chat", "llm_endpoints_exhausted", "warning", "fallback",
            error_policy="required",
        ),
        AuditEventDefinition(
            "chat", "llm_endpoint_state_write_failed", "warning", "degraded",
            error_policy="required", metadata_validator=_endpoint_index,
        ),
        AuditEventDefinition(
            "chat", "compression_fallback", "warning", "degraded",
            error_policy="required",
        ),
        AuditEventDefinition(
            "chat", "interactive_history_load_failed", "error", "error",
            error_policy="required", metadata_validator=_conversation,
        ),
        AuditEventDefinition(
            "chat", "interactive_history_write_failed", "warning", "degraded",
            error_policy="required",
        ),
        AuditEventDefinition(
            "chat", "completion_load_failed", "warning", "degraded",
            error_policy="required", metadata_validator=_completion,
        ),
        AuditEventDefinition(
            "chat", "interactive_prompt_failed", "warning", "degraded",
            error_policy="required", metadata_validator=_prompt,
        ),
        AuditEventDefinition("chat", "turn_retry", "info", "retry",
                             metadata_validator=_turn_retry),
        AuditEventDefinition(
            "chat", "activity_transport_degraded", "warning", "degraded",
            error_policy="required", metadata_validator=_activity,
        ),
        AuditEventDefinition(
            "chat", "interactive_send_failed", "error", "error",
            error_policy="required",
        ),
        AuditEventDefinition(
            "chat", "interactive_cleanup_failed", "error", "error",
            error_policy="required", metadata_validator=_cleanup,
        ),
    )
    return definitions

_MESSAGES: dict[ChatAuditEvent, str] = {
    "daemon_chat_completed": "daemon chat request completed",
    "daemon_chat_failed": "daemon chat request failed",
    "one_shot_chat_completed": "one-shot chat turn completed",
    "one_shot_chat_failed": "one-shot chat turn failed",
    "final_response_completed": "final response accepted",
    "llm_endpoint_retry": "LLM endpoint error; retrying",
    "llm_retry_suppressed_after_tool_call": (
        "LLM retry suppressed after tool execution"
    ),
    "llm_endpoints_exhausted": "LLM endpoints exhausted",
    "llm_endpoint_state_write_failed": "LLM endpoint state write failed",
    "compression_fallback": "Conversation compression used local fallback",
    "interactive_history_load_failed": "Interactive history load failed",
    "interactive_history_write_failed": "Interactive history write failed",
    "completion_load_failed": "Interactive completion load failed",
    "interactive_prompt_failed": "Interactive prompt degraded",
    "turn_retry": "Chat turn transport retry scheduled",
    "activity_transport_degraded": "Activity transport degraded",
    "interactive_send_failed": "Interactive chat send failed",
    "interactive_cleanup_failed": "Interactive session cleanup failed",
}


CHAT_AUDIT = AuditCatalog[ChatAuditEvent](_definitions(), _MESSAGES)
