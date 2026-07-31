"""Adapters from frontend-neutral feature events to runtime events."""

from __future__ import annotations

from nuself.runtime.event_payloads import RuntimeLogEventPayload
from nuself.runtime.events import EventPublisher
from nuself.runtime.frontend import FrontendEvent


class RuntimeFrontendEventSink:
    """Publish feature activity through the existing typed event runtime."""

    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    def publish(self, event: FrontendEvent) -> None:
        self._publisher.publish(
            producer="chat",
            name="tool.activity",
            payload=RuntimeLogEventPayload(
                message=_message(event),
                level="info",
                status=_STATUS[event.kind],
                metadata={
                    "frontend_event": event.kind,
                    "service_component": event.component,
                    "operation": event.operation,
                    **event.fields,
                },
            ).to_mapping(),
        )


_STATUS = {
    "approval_requested": "pending",
    "approval_decided": "decided",
}


def _message(event: FrontendEvent) -> str:
    action = (
        "requested"
        if event.kind == "approval_requested"
        else "decided"
    )
    return f"Approval {action} for {event.operation}"
