from __future__ import annotations

from nuself.runtime.event_payloads import RuntimeLogEventPayload
from nuself.runtime.events import EventPublisher
from nuself.runtime.frontend import FrontendEvent
from nuself.runtime.frontend_adapter import RuntimeFrontendEventSink
from nuself.runtime.messages import RuntimeEnvelope


def test_frontend_event_uses_existing_runtime_event_boundary() -> None:
    publisher = EventPublisher()
    captured: list[RuntimeEnvelope] = []
    publisher.attach_projection(captured.append)

    RuntimeFrontendEventSink(publisher).publish(
        FrontendEvent(
            kind="approval_requested",
            component="reasoning",
            operation="reason_export",
            fields={"action": "export"},
        )
    )

    assert len(captured) == 1
    event = captured[0]
    assert event.producer == "chat"
    assert event.name == "tool.activity"
    payload = RuntimeLogEventPayload.from_mapping(event.payload)
    assert payload.status == "pending"
    assert payload.metadata == {
        "frontend_event": "approval_requested",
        "service_component": "reasoning",
        "operation": "reason_export",
        "action": "export",
    }
