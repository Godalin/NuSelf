from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nuself.agent.tools.decorated import materialize_tool
from nuself.runtime.feature_execution import (
    FeatureAuditRecord,
    FeatureConfirmationDeclined,
    FeatureExecutor,
)
from nuself.runtime.events import EventPublisher
from nuself.runtime.event_payloads import RuntimeLogEventPayload
from nuself.runtime.messages import RuntimeEnvelope
from nuself.runtime.features import (
    FeaturePolicyConflictError,
    audited,
    component,
    feature_spec,
    mutating,
    observed,
    readonly,
    requires_confirmation,
    tool,
)
from nuself.runtime.frontend import (
    ApprovalDecision,
    ApprovalRequest,
)


@dataclass
class Audits:
    values: list[FeatureAuditRecord] = field(
        default_factory=lambda: list[FeatureAuditRecord]()
    )

    def write(self, record: FeatureAuditRecord) -> None:
        self.values.append(record)


class Approve:
    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        assert request.action == "archive"
        return ApprovalDecision(
            True,
            approver="tester",
            input_kind="affirmative",
        )


class Decline:
    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        del request
        return ApprovalDecision(False, input_kind="declined")


def test_orthogonal_decorators_compose_without_wrapping_function() -> None:
    def implementation(value: str) -> str:
        return value

    decorated = audited("memory_archived")(
        observed(
            requires_confirmation(
                action="archive",
                resource="memory",
            )(
                mutating(component("memory")(tool(name="memory_archive")(implementation)))
            )
        )
    )

    assert decorated is implementation
    spec = feature_spec(decorated)
    assert spec.tool is not None
    assert spec.tool.name == "memory_archive"
    assert spec.component == "memory"
    assert spec.effect == "mutating"
    assert spec.confirmation is not None
    assert spec.observation is not None
    assert spec.audit is not None


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
        approvals=Approve(),
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
        payload.metadata["frontend_event"]
        for payload in payloads
        if payload.metadata is not None
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


def test_declined_confirmation_does_not_call_feature() -> None:
    called = False

    @tool
    @component("memory")
    @mutating
    @requires_confirmation(action="archive", resource="memory")
    def archive() -> None:
        nonlocal called
        called = True

    with pytest.raises(FeatureConfirmationDeclined):
        FeatureExecutor(approvals=Decline()).invoke(archive)

    assert called is False


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
        "effect": "readonly",
        "confirmation_required": False,
        "observed": False,
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
