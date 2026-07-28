"""Shared runtime infrastructure primitives."""

from nuself.runtime.cleanup import CleanupFailure, run_cleanup_steps
from nuself.runtime.context import (
    RuntimeContext,
    bind_runtime_context,
    current_runtime_context,
    runtime_context,
    use_runtime_context,
)
from nuself.runtime.diagnostics import emit_runtime_warning
from nuself.runtime.definitions import (
    DefinitionRegistry,
    DefinitionRegistrySealedError,
    DuplicateDefinitionError,
    UnknownDefinitionError,
)
from nuself.runtime.event_definitions import (
    CORE_EVENT_DEFINITIONS,
    DuplicateEventDefinitionError,
    EventDefinitionRegistry,
    EventDefinitionRegistrySealedError,
    EventPayloadValidator,
    RuntimeEventDefinition,
    UnknownEventDefinitionError,
    build_event_definition_registry,
)
from nuself.runtime.event_payloads import (
    RuntimeLogEventPayload,
    RuntimeLogLevel,
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
    HandlerRegistryUnsealedError,
    UnknownHandlerError,
)
from nuself.runtime.jobs import JobMessage, JobPayload, JobSink
from nuself.runtime.job_definitions import (
    DuplicateJobDefinitionError,
    JobDataValidator,
    JobDefinitionRegistry,
    JobDefinitionRegistrySealedError,
    RuntimeJobDefinition,
    UnknownJobDefinitionError,
    build_job_definition_registry,
)
from nuself.runtime.messages import (
    RUNTIME_SCHEMA_VERSION,
    MessageKind,
    RuntimeEnvelope,
    decode_json_value,
    encode_json_value,
    freeze_json_value,
    thaw_json_value,
)
from nuself.runtime.workers import (
    OwnedWorker,
    WorkerLifecycleSnapshot,
    WorkerLifecycleState,
)

__all__ = [
    "CORE_EVENT_DEFINITIONS",
    "RUNTIME_SCHEMA_VERSION",
    "CleanupFailure",
    "DefinitionRegistry",
    "DefinitionRegistrySealedError",
    "DuplicateDefinitionError",
    "DuplicateEventDefinitionError",
    "DuplicateHandlerError",
    "DuplicateJobDefinitionError",
    "EventDefinitionRegistry",
    "EventDefinitionRegistrySealedError",
    "EventPayloadValidator",
    "EventDeliveryError",
    "EventDeliveryFailure",
    "EventPublisher",
    "EventSubscriber",
    "EventSubscription",
    "HandlerRegistry",
    "HandlerMiddleware",
    "HandlerRegistrySealedError",
    "HandlerRegistryUnsealedError",
    "JobMessage",
    "JobDataValidator",
    "JobDefinitionRegistry",
    "JobDefinitionRegistrySealedError",
    "JobPayload",
    "JobSink",
    "MessageKind",
    "OwnedWorker",
    "RuntimeContext",
    "RuntimeEnvelope",
    "RuntimeEventDefinition",
    "RuntimeJobDefinition",
    "RuntimeLogEventPayload",
    "RuntimeLogLevel",
    "UnknownDefinitionError",
    "UnknownEventDefinitionError",
    "UnknownHandlerError",
    "UnknownJobDefinitionError",
    "WorkerLifecycleSnapshot",
    "WorkerLifecycleState",
    "build_event_definition_registry",
    "build_job_definition_registry",
    "bind_runtime_context",
    "current_runtime_context",
    "decode_json_value",
    "encode_json_value",
    "emit_runtime_warning",
    "freeze_json_value",
    "runtime_context",
    "run_cleanup_steps",
    "thaw_json_value",
    "use_runtime_context",
]
