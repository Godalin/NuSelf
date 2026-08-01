from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from nuself.agent.chat import audit
from nuself.runtime import observability
from nuself.runtime.audit_definitions import (
    AuditSchemaError,
    UnknownAuditDefinitionError,
)

_CANONICAL: tuple[tuple[str, dict[str, object]], ...] = (
    ("daemon_chat_completed", {}),
    ("daemon_chat_failed", {}),
    ("one_shot_chat_completed", {}),
    ("one_shot_chat_failed", {}),
    ("final_response_completed", {"epistemic_status": "inferred"}),
    ("llm_endpoint_retry", {"endpoint_index": 0, "model": "model"}),
    (
        "llm_retry_suppressed_after_tool_call",
        {"endpoint_index": 0, "model": "model"},
    ),
    ("llm_endpoints_exhausted", {}),
    ("llm_endpoint_state_write_failed", {"endpoint_index": 0}),
    ("compression_fallback", {}),
    ("interactive_history_load_failed", {"conversation_id": "thread-1"}),
    ("interactive_history_write_failed", {}),
    ("completion_load_failed", {"completion": "conversations"}),
    ("interactive_prompt_failed", {"fallback": "builtin_input"}),
    (
        "turn_retry",
        {
            "attempt": 2,
            "max_attempts": 2,
            "failure_phase": "receive",
            "request_may_have_completed": True,
        },
    ),
    (
        "activity_transport_degraded",
        {
            "stage": "poll",
            "error_kind": "connection",
            "has_subscription": True,
            "failure_phase": "receive",
            "retryable": True,
            "request_may_have_completed": True,
        },
    ),
    ("interactive_send_failed", {}),
    (
        "interactive_cleanup_failed",
        {"steps": ["transcript.auto_save"], "primary_failed": False},
    ),
)


def test_chat_registry_owns_complete_direct_taxonomy() -> None:
    assert {
        definition.event
        for definition in audit.CHAT_AUDIT_REGISTRY.definitions
    } == {event for event, _ in _CANONICAL}


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_chat_definitions_accept_canonical_payloads(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.CHAT_AUDIT_REGISTRY.resolve("chat", event)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=(
            "caught failure"
            if definition.error_policy == "required"
            else None
        ),
        metadata=metadata,
    )


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_chat_definitions_reject_private_or_unknown_metadata(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.CHAT_AUDIT_REGISTRY.resolve("chat", event)
    with pytest.raises(AuditSchemaError, match="metadata"):
        definition.validate(
            level=definition.level,
            status=definition.status,
            error=(
                "caught failure"
                if definition.error_policy == "required"
                else None
            ),
            metadata={**metadata, "previous_error": "private failure"},
        )


def test_chat_audit_rejects_unknown_event_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(audit, "write_observed_log_event", unexpected_sink)
    with pytest.raises(UnknownAuditDefinitionError):
        audit.write_chat_audit(
            cast(audit.ChatAuditEvent, "daemon_chat_compeleted"),
            project_root=tmp_path,
        )
    assert sink_calls == 0


def test_chat_retry_rejects_endpoint_url_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(
        observability,
        "report_observed_failure",
        unexpected_sink,
    )
    with pytest.raises(AuditSchemaError, match="metadata"):
        audit.report_chat_failure(
            RuntimeError("provider failed"),
            event="llm_endpoint_retry",
            project_root=tmp_path,
            metadata={
                "endpoint_index": 0,
                "model": "model",
                "base_url": "https://secret.invalid",
            },
        )
    assert sink_calls == 0
