import ast
import warnings
from pathlib import Path

import pytest

import nuself.runtime.observability as observability
from nuself.logs import LogAppendLifecycleError, read_log_events
from nuself.runtime.events import EventPublisher
from nuself.runtime.event_definitions import UnknownEventDefinitionError
from nuself.runtime.diagnostics import (
    diagnostic_exception_chain,
    diagnostic_exception_message,
    emit_runtime_warning,
    sanitize_diagnostic_metadata,
)
from nuself.runtime.observability import (
    decode_observed_record,
    publish_observed_event,
    report_observed_failure,
    run_observed_best_effort,
    write_observed_log_event,
)


def test_domains_do_not_rebuild_observed_log_projection() -> None:
    source_root = Path(__file__).parents[1] / "src" / "nuself"
    violations: list[str] = []
    for path in source_root.rglob("*.py"):
        if path == source_root / "runtime" / "observability.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            if not isinstance(callee, ast.Name):
                continue
            if callee.id != "run_observed_best_effort" or not node.args:
                continue
            operation = node.args[0]
            if not isinstance(operation, ast.Lambda):
                continue
            for nested in ast.walk(operation.body):
                if (
                    isinstance(nested, ast.Call)
                    and isinstance(nested.func, ast.Name)
                    and nested.func.id == "write_log_event"
                ):
                    relative = path.relative_to(source_root)
                    violations.append(f"{relative}:{node.lineno}")
    assert violations == []


def test_diagnostic_exception_chain_preserves_unique_cause_messages() -> None:
    try:
        try:
            raise ValueError("root")
        except ValueError as exc:
            raise RuntimeError("outer") from exc
    except RuntimeError as exc:
        assert diagnostic_exception_chain(exc) == "outer <- root"


def test_diagnostic_exception_chain_respects_suppressed_context() -> None:
    try:
        try:
            raise OSError("private path")
        except OSError:
            raise RuntimeError("safe summary") from None
    except RuntimeError as exc:
        assert diagnostic_exception_chain(exc) == "safe summary"


def test_diagnostic_exception_chain_survives_broken_renderer() -> None:
    class BrokenMessageError(RuntimeError):
        def __str__(self) -> str:
            raise KeyboardInterrupt

    try:
        raise BrokenMessageError() from ValueError("root")
    except BrokenMessageError as exc:
        assert (
            diagnostic_exception_chain(exc)
            == "BrokenMessageError <- root"
        )


def test_diagnostic_exception_message_is_safe_and_sanitized() -> None:
    class BrokenMessageError(RuntimeError):
        def __str__(self) -> str:
            raise KeyboardInterrupt

    assert (
        diagnostic_exception_message(BrokenMessageError())
        == "BrokenMessageError"
    )
    assert diagnostic_exception_message(
        RuntimeError("failed password=private-value")
    ) == "failed password=***"


def test_diagnostic_metadata_is_recursively_copied_and_sanitized() -> None:
    metadata: dict[str, object] = {
        "api_key": "top-secret",
        "apiKey": "camel-secret",
        "safe_id": "worker-1",
        "nested": {
            "authorization": "Bearer nested-secret",
            "detail": "request failed token=embedded-secret",
        },
        "items": [
            {
                "smtp.password": "mail-secret",
                "status": "failed",
            }
        ],
    }

    sanitized = sanitize_diagnostic_metadata(metadata)

    assert sanitized == {
        "api_key": "***",
        "apiKey": "***",
        "safe_id": "worker-1",
        "nested": {
            "authorization": "***",
            "detail": "request failed token=***",
        },
        "items": [
            {
                "smtp.password": "***",
                "status": "failed",
            }
        ],
    }
    assert metadata["api_key"] == "top-secret"
    assert metadata["apiKey"] == "camel-secret"
    assert metadata["nested"] == {
        "authorization": "Bearer nested-secret",
        "detail": "request failed token=embedded-secret",
    }


def test_best_effort_returns_none_and_writes_structured_failure(
    tmp_path: Path,
) -> None:
    def fail() -> None:
        raise RuntimeError("trace unavailable")

    result = run_observed_best_effort(
        fail,
        component="memory",
        event="trace_recording_failed",
        message="Could not record trace",
        project_root=tmp_path,
        metadata={"memory_id": "m1"},
    )

    assert result is None
    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "trace_recording_failed"
    assert event.level == "warning"
    assert event.status == "degraded"
    assert event.error == "trace unavailable"
    assert event.metadata == {"memory_id": "m1"}


def test_observed_failure_redacts_credentials_from_compact_chain(
    tmp_path: Path,
) -> None:
    provider_secret = "provider-secret-value"

    def fail() -> None:
        raise RuntimeError(
            f"provider failed api_key={provider_secret}"
        )

    result = run_observed_best_effort(
        fail,
        component="chat",
        event="provider_failed",
        message="Provider request failed",
        project_root=tmp_path,
    )

    assert result is None
    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.error == "provider failed api_key=***"
    assert provider_secret not in str(event.to_record())


def test_observed_failure_sanitizes_metadata_before_persistence(
    tmp_path: Path,
) -> None:
    metadata: dict[str, object] = {
        "client_secret": "private-value",
        "context": {
            "url": "https://provider.invalid?access_token=query-secret",
        },
    }

    report_observed_failure(
        RuntimeError("provider failed"),
        component="chat",
        event="provider_failed",
        message="Provider request failed",
        project_root=tmp_path,
        metadata=metadata,
    )

    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.to_record()["metadata"] == {
        "client_secret": "***",
        "context": {
            "url": "https://provider.invalid?access_token=***",
        },
    }
    assert metadata["client_secret"] == "private-value"


def test_invalid_observed_failure_metadata_uses_terminal_warning(
    tmp_path: Path,
) -> None:
    private_object = object()

    with pytest.warns(
        RuntimeWarning,
        match="value is not JSON-safe: object",
    ):
        report_observed_failure(
            RuntimeError("provider failed"),
            component="chat",
            event="provider_failed",
            message="Provider request failed",
            project_root=tmp_path,
            metadata={"context": private_object},
        )

    assert read_log_events(project_root=tmp_path) == []


def test_observed_log_reports_uncertain_write_without_retrying_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_log_event = observability.write_log_event
    close_error = OSError("uncertain close")
    calls: list[str] = []

    def fail_original_then_write_diagnostic(
        component: object,
        event: str,
        message: object,
        **kwargs: object,
    ) -> object:
        del component, message
        calls.append(event)
        if len(calls) == 1:
            raise LogAppendLifecycleError(
                primary_error=None,
                rollback_error=None,
                close_error=close_error,
                record_may_have_persisted=True,
            ) from close_error
        return write_log_event(
            "reflection",
            event,
            "diagnostic",
            **kwargs,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(
        observability,
        "write_log_event",
        fail_original_then_write_diagnostic,
    )

    result = write_observed_log_event(
        "reflection",
        "cycle_completed",
        "completed",
        project_root=tmp_path,
        failure_metadata={"owner": "scheduler"},
    )

    assert result is None
    assert calls == ["cycle_completed", "audit_projection_failed"]
    [diagnostic] = read_log_events(
        project_root=tmp_path,
        component="reflection",
    )
    assert diagnostic.event == "audit_projection_failed"
    assert diagnostic.metadata == {
        "audit_event": "cycle_completed",
        "owner": "scheduler",
    }


def test_observed_event_reports_subscriber_failure_and_returns_envelope(
    tmp_path: Path,
) -> None:
    publisher = EventPublisher()

    def fail_subscriber(_event: object) -> None:
        raise RuntimeError("subscriber unavailable")

    publisher.subscribe(fail_subscriber)

    result = publish_observed_event(
        publisher,
        name="turn.started",
        producer="chat",
        payload={"message": "started"},
        project_root=tmp_path,
        failure_component="chat",
        failure_event="turn_event_delivery_failed",
        failure_message="Could not deliver turn event",
        failure_metadata={"lifecycle_event": "turn.started"},
    )

    assert result is not None
    assert result.name == "turn.started"
    [event] = read_log_events(
        project_root=tmp_path,
        component="chat",
    )
    assert event.event == "turn_event_delivery_failed"
    assert event.error is not None
    assert "subscriber unavailable" in event.error


def test_observed_event_producer_contract_failure_propagates(
    tmp_path: Path,
) -> None:
    publisher = EventPublisher()

    with pytest.raises(UnknownEventDefinitionError):
        publish_observed_event(
            publisher,
            name="turn.started",
            producer="daemon",
            payload={"message": "invalid producer"},
            project_root=tmp_path,
            failure_component="chat",
            failure_event="turn_event_delivery_failed",
            failure_message="Could not deliver turn event",
        )

    assert read_log_events(project_root=tmp_path) == []


def test_observed_event_payload_validation_failure_propagates(
    tmp_path: Path,
) -> None:
    publisher = EventPublisher()

    with pytest.raises(TypeError, match="not JSON-safe"):
        publish_observed_event(
            publisher,
            name="turn.started",
            producer="chat",
            payload={"metadata": {"invalid": object()}},
            project_root=tmp_path,
            failure_component="chat",
            failure_event="turn_event_delivery_failed",
            failure_message="Could not deliver turn event",
        )

    assert read_log_events(project_root=tmp_path) == []


def test_best_effort_propagates_undeclared_exception(
    tmp_path: Path,
) -> None:
    def fail() -> None:
        raise OSError("storage unavailable")

    with pytest.raises(OSError, match="storage unavailable"):
        run_observed_best_effort(
            fail,
            component="memory",
            event="validation_failed",
            message="Recoverable validation failed",
            project_root=tmp_path,
            errors=(ValueError,),
        )

    assert read_log_events(
        project_root=tmp_path,
        component="memory",
    ) == []


def test_observed_failure_supports_authoritative_error_severity(
    tmp_path: Path,
) -> None:
    report_observed_failure(
        RuntimeError("worker failed"),
        component="daemon",
        event="worker_exited_unexpectedly",
        message="worker exited",
        project_root=tmp_path,
        metadata={"worker": "memory_curator"},
        level="error",
        status="error",
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.level == "error"
    assert event.status == "error"
    assert event.error == "worker failed"


def test_best_effort_warns_when_structured_sink_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="memory/trace_recording_failed.*primary failed.*disk full",
    ):
        result = run_observed_best_effort(
            lambda: (_ for _ in ()).throw(RuntimeError("primary failed")),
            component="memory",
            event="trace_recording_failed",
            message="Could not record trace",
        )

    assert result is None


def test_terminal_runtime_warning_cannot_be_promoted_to_primary_failure() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        emit_runtime_warning("secondary diagnostic")


def test_terminal_runtime_warning_cannot_be_failed_by_warning_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_warning_hook(*args: object, **kwargs: object) -> None:
        raise OSError("warning hook unavailable")

    monkeypatch.setattr(
        "nuself.runtime.diagnostics.warnings.showwarning",
        fail_warning_hook,
    )

    emit_runtime_warning("secondary diagnostic")


@pytest.mark.parametrize(
    ("wire", "expected_id"),
    [
        ({"id": "mem_bad", "private_body": "secret"}, "mem_bad"),
        ({"private_body": "secret"}, "<unknown>"),
    ],
)
def test_record_decode_failure_reports_identity_without_payload(
    tmp_path: Path,
    wire: dict[str, object],
    expected_id: str,
) -> None:
    def decode(record: dict[str, object]) -> str:
        raise ValueError("missing required title")

    assert (
        decode_observed_record(
            wire,
            decode,
            component="memory",
            collection="memory_entries",
            project_root=tmp_path,
        )
        is None
    )

    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "memory_entries",
        "record_id": expected_id,
    }
    assert "secret" not in str(event.to_record())


def test_record_decode_does_not_hide_unexpected_errors(tmp_path: Path) -> None:
    def decode(record: dict[str, object]) -> str:
        raise RuntimeError("programming failure")

    with pytest.raises(RuntimeError, match="programming failure"):
        decode_observed_record(
            {"id": "mem_bad"},
            decode,
            component="memory",
            collection="memory_entries",
            project_root=tmp_path,
        )
