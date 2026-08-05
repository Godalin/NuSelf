from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from nuself.agent.tools.decorated import materialize_tool
from nuself.runtime.feature.execution import (
    FeatureAuditRecord,
    FeatureExecutor,
    ToolEffectDeclined,
)
from nuself.agent.effect import GraphToolEffectPort
from nuself.runtime.feature.effect import (
    ApprovalEffectDecision,
    ApprovalEffectRequest,
    ToolEffectRequired,
    ToolEffectResolution,
)
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.messages import RuntimeEnvelope
from nuself.runtime.feature.policy import (
    ApprovalEffectPolicy,
    AuditEffectPolicy,
    FeaturePolicyConflictError,
    ObservationEffectPolicy,
    audited,
    compact,
    component,
    feature_spec,
    mutating,
    observed,
    readonly,
    requires_confirmation,
    tool,
)
from nuself.log.reader import read_log_events
from nuself.log.store import runtime_event_log_sink


@dataclass
class Audits:
    values: list[FeatureAuditRecord] = field(
        default_factory=lambda: list[FeatureAuditRecord]()
    )

    def write(self, record: FeatureAuditRecord) -> None:
        self.values.append(record)


class Approve:
    def resolve(
        self,
        request: ApprovalEffectRequest,
    ) -> ToolEffectResolution:
        assert request.action == "archive"
        return ToolEffectResolution(
            request,
            ApprovalEffectDecision(
                True,
                approver="tester",
                input_kind="affirmative",
            ),
        )


class Decline:
    def resolve(
        self,
        request: ApprovalEffectRequest,
    ) -> ToolEffectResolution:
        return ToolEffectResolution(
            request,
            ApprovalEffectDecision(False, input_kind="declined"),
        )


def test_graph_effect_port_challenges_outside_a_graph() -> None:
    request = ApprovalEffectRequest(
        component="memory",
        operation="memory_create",
        action="create",
        resource="memory",
        risk="reversible",
        summary="Create exact memory",
    )
    port = GraphToolEffectPort()

    with pytest.raises(ToolEffectRequired) as missing:
        port.resolve(request)
    assert missing.value.request == request


def test_orthogonal_decorators_compose_without_wrapping_function() -> None:
    def implementation(value: str) -> str:
        return value

    decorated = audited("memory_archived")(
        compact(observed(
            requires_confirmation(
                action="archive",
                resource="memory",
            )(
                mutating(component("memory")(tool(name="memory_archive")(implementation)))
            )
        ))
    )

    assert decorated is implementation
    spec = feature_spec(decorated)
    assert spec.tool is not None
    assert spec.tool.name == "memory_archive"
    assert spec.component == "memory"
    assert spec.execution == "mutating"
    assert any(isinstance(effect, ApprovalEffectPolicy) for effect in spec.effects)
    assert any(isinstance(effect, ObservationEffectPolicy) for effect in spec.effects)
    assert spec.compact is not None
    assert any(isinstance(effect, AuditEffectPolicy) for effect in spec.effects)


def test_effect_collection_is_canonical_across_decorator_order() -> None:
    def first() -> None:
        pass

    def second() -> None:
        pass

    observed(audited("changed")(
        requires_confirmation(action="change", resource="memory")(first)
    ))
    audited("changed")(requires_confirmation(
        action="change",
        resource="memory",
    )(observed(second)))

    assert tuple(type(effect) for effect in feature_spec(first).effects) == (
        ApprovalEffectPolicy,
        ObservationEffectPolicy,
        AuditEffectPolicy,
    )
    assert tuple(type(effect) for effect in feature_spec(second).effects) == (
        ApprovalEffectPolicy,
        ObservationEffectPolicy,
        AuditEffectPolicy,
    )


def test_conflicting_effect_declarations_fail_at_composition() -> None:
    @readonly
    def feature() -> None:
        pass

    with pytest.raises(
        FeaturePolicyConflictError,
        match="both readonly and mutating",
    ):
        mutating(feature)


def test_executor_uses_ports_and_emits_safe_events_and_audit() -> None:
    events = EventPublisher()
    captured: list[RuntimeEnvelope] = []
    events.attach_projection(captured.append)
    audits = Audits()

    @tool(name="memory_archive")
    @component("memory")
    @mutating
    @requires_confirmation(action="archive", resource="memory")
    @observed
    @audited("memory_archived")
    def archive(secret: str) -> str:
        return f"archived {secret}"

    result = FeatureExecutor(
        effects=Approve(),
        events=events,
        audits=audits,
    ).invoke(archive, "private-value")

    assert result == "archived private-value"
    payloads = [
        RuntimeLogEventPayload.from_mapping(event.payload)
        for event in captured
    ]
    assert all(payload.metadata is not None for payload in payloads)
    assert [
        payload.metadata.get("frontend_event")
        for payload in payloads
        if payload.metadata is not None
        and "frontend_event" in payload.metadata
    ] == [
        "approval_requested",
        "approval_decided",
    ]
    assert "private-value" not in repr(captured)
    assert audits.values == [
        FeatureAuditRecord(
            component="memory",
            event="memory_archived",
            operation="memory_archive",
            outcome="completed",
        )
    ]
    assert [
        event.name
        for event in captured
        if event.name.startswith("feature.")
    ] == [
        "feature.started",
        "feature.completed",
    ]


def test_observed_feature_publishes_safe_failure_lifecycle() -> None:
    events = EventPublisher()
    captured: list[RuntimeEnvelope] = []
    events.attach_projection(captured.append)

    @component("memory")
    @observed
    def fail(secret: str) -> None:
        raise RuntimeError(secret)

    with pytest.raises(RuntimeError, match="private-value"):
        FeatureExecutor(events=events).invoke(fail, "private-value")

    assert [event.name for event in captured] == [
        "feature.started",
        "feature.failed",
    ]
    assert "private-value" not in repr(captured)
    failed = RuntimeLogEventPayload.from_mapping(captured[-1].payload)
    assert failed.metadata == {
        "service_component": "memory",
        "operation": "fail",
        "error_type": "RuntimeError",
    }


def test_unobserved_feature_publishes_no_lifecycle() -> None:
    events = EventPublisher()
    captured: list[RuntimeEnvelope] = []
    events.attach_projection(captured.append)

    def plain() -> str:
        return "done"

    assert FeatureExecutor(events=events).invoke(plain) == "done"
    assert captured == []


def test_observed_feature_uses_the_normal_log_projection(tmp_path: Path) -> None:
    events = EventPublisher()
    events.attach_projection(runtime_event_log_sink(tmp_path))

    @component("memory")
    @observed
    def feature() -> None:
        pass

    FeatureExecutor(events=events).invoke(feature)

    assert [
        event.event
        for event in read_log_events(project_root=tmp_path, component="chat")
    ] == ["feature.started", "feature.completed"]


def test_declined_confirmation_does_not_call_feature() -> None:
    called = False

    @tool
    @component("memory")
    @mutating
    @requires_confirmation(action="archive", resource="memory")
    def archive() -> None:
        nonlocal called
        called = True

    with pytest.raises(ToolEffectDeclined):
        FeatureExecutor(effects=Decline()).invoke(archive)

    assert called is False


def test_missing_approval_frontend_is_not_reported_as_user_decline() -> None:
    @tool
    @component("memory")
    @mutating
    @requires_confirmation(action="create", resource="memory")
    def create() -> str:
        return "created"

    with pytest.raises(ToolEffectRequired) as captured:
        FeatureExecutor().invoke(create)

    assert captured.value.request.operation == "create"


def test_materialized_tool_preserves_framework_boundary() -> None:
    @tool(name="memory_count", description="Count memories.")
    @component("memory")
    @readonly
    def count_memory() -> str:
        return "3"

    framework_tool = materialize_tool(
        count_memory,
        executor=FeatureExecutor(),
    )

    assert framework_tool.name == "memory_count"
    assert framework_tool.invoke({}) == "3"
    assert framework_tool.tags == ["readonly"]
    assert framework_tool.metadata == {
        "service_component": "memory",
        "execution": "readonly",
        "confirmation_required": False,
        "observed": False,
        "compact": False,
        "audit_event": None,
    }


def test_secondary_event_and_audit_failures_do_not_replace_result() -> None:
    class BrokenAudits:
        def write(self, record: FeatureAuditRecord) -> None:
            del record
            raise OSError("audit unavailable")

    @tool
    @component("memory")
    @mutating
    @observed
    @audited("memory_updated")
    def update() -> str:
        return "primary"

    broken_events = EventPublisher()
    def fail_projection(event: RuntimeEnvelope) -> None:
        del event
        raise OSError("event unavailable")

    broken_events.attach_projection(fail_projection)
    assert FeatureExecutor(
        events=broken_events,
        audits=BrokenAudits(),
    ).invoke(update) == "primary"
