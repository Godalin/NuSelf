"""Shared runtime infrastructure primitives."""

from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
    use_runtime_context,
)
from nuself.runtime.event_definitions import (
    CORE_EVENT_DEFINITIONS,
    DuplicateEventDefinitionError,
    EventDefinitionRegistry,
    EventDefinitionRegistrySealedError,
    RuntimeEventDefinition,
    UnknownEventDefinitionError,
    build_event_definition_registry,
)
from nuself.runtime.events import (
    EventDeliveryError,
    EventDeliveryFailure,
    EventPublisher,
    EventSubscriber,
    EventSubscription,
)
from nuself.runtime.handlers import (
    DuplicateHandlerError,
    HandlerMiddleware,
    HandlerRegistry,
    HandlerRegistrySealedError,
    UnknownHandlerError,
)
from nuself.runtime.jobs import JobMessage, JobSink
from nuself.runtime.messages import (
    RUNTIME_SCHEMA_VERSION,
    MessageKind,
    RuntimeEnvelope,
)
from nuself.runtime.workers import (
    OwnedWorker,
    WorkerLifecycleSnapshot,
    WorkerLifecycleState,
)

__all__ = [
    "CORE_EVENT_DEFINITIONS",
    "RUNTIME_SCHEMA_VERSION",
    "DuplicateEventDefinitionError",
    "DuplicateHandlerError",
    "EventDefinitionRegistry",
    "EventDefinitionRegistrySealedError",
    "EventDeliveryError",
    "EventDeliveryFailure",
    "EventPublisher",
    "EventSubscriber",
    "EventSubscription",
    "HandlerRegistry",
    "HandlerMiddleware",
    "HandlerRegistrySealedError",
    "JobMessage",
    "JobSink",
    "MessageKind",
    "OwnedWorker",
    "RuntimeContext",
    "RuntimeEnvelope",
    "RuntimeEventDefinition",
    "UnknownEventDefinitionError",
    "UnknownHandlerError",
    "WorkerLifecycleSnapshot",
    "WorkerLifecycleState",
    "build_event_definition_registry",
    "current_runtime_context",
    "runtime_context",
    "use_runtime_context",
]
