"""Registered semantic contracts for typed runtime jobs."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from nuself.runtime.jobs import JobMessage

from nuself.runtime.definitions import (
    DefinitionRegistry,
    DefinitionRegistrySealedError,
    DefinitionRegistryUnsealedError,
    DuplicateDefinitionError,
    UnknownDefinitionError,
)
from nuself.runtime.identities import (
    require_identity_segment,
    require_runtime_event_name,
)
from nuself.runtime.context import current_runtime_context
from nuself.runtime.messages import RuntimeEnvelope

JobDataValidator = Callable[[str, Mapping[str, object]], None]


class JobDefinitionInput(Protocol):
    """Typed job surface required by the semantic registry."""

    @property
    def name(self) -> str: ...

    @property
    def producer(self) -> str: ...

    @property
    def payload(self) -> Mapping[str, object]: ...


class DuplicateJobDefinitionError(ValueError):
    """Raised when a job name is registered twice."""


class JobDefinitionRegistrySealedError(RuntimeError):
    """Raised when a sealed job-definition registry is mutated."""


class JobDefinitionRegistryUnsealedError(RuntimeError):
    """Raised when job construction starts before composition is sealed."""


class UnknownJobDefinitionError(LookupError):
    """Raised when queue ingress receives an unregistered job name."""


@dataclass(frozen=True)
class RuntimeJobDefinition:
    """Stable semantic ownership for one typed job wake-up."""

    name: str
    description: str
    producers: frozenset[str]
    data_validator: JobDataValidator | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        require_runtime_event_name(self.name)
        if not self.description:
            raise ValueError("job definition description must not be empty")
        if not self.producers:
            raise ValueError("job definition requires at least one producer")
        for producer in self.producers:
            require_identity_segment(
                producer,
                label="runtime job producer",
            )
        if (
            self.data_validator is not None
            and not callable(self.data_validator)
        ):
            raise TypeError("job data validator must be callable")

    def validate(
        self,
        *,
        producer: str,
        data: Mapping[str, object],
    ) -> None:
        if producer not in self.producers:
            raise ValueError(
                f"runtime job producer is not allowed for {self.name!r}"
            )
        if self.data_validator is not None:
            self.data_validator(producer, data)


class JobDefinitionRegistry:
    """Duplicate-safe job definitions sealed after composition."""

    def __init__(self) -> None:
        self._registry = DefinitionRegistry[str, RuntimeJobDefinition](
            lambda definition: definition.name,
            namespace="runtime job",
        )

    def register(
        self,
        definition: RuntimeJobDefinition,
    ) -> JobDefinitionRegistry:
        try:
            self._registry.register(definition)
        except DefinitionRegistrySealedError as exc:
            raise JobDefinitionRegistrySealedError(
                "job definition registry is sealed"
            ) from exc
        except DuplicateDefinitionError as exc:
            raise DuplicateJobDefinitionError(
                f"job definition already registered: {exc.key!r}"
            ) from exc
        return self

    def resolve(self, name: str) -> RuntimeJobDefinition:
        try:
            return self._registry.resolve(name)
        except DefinitionRegistryUnsealedError as exc:
            raise JobDefinitionRegistryUnsealedError(
                "job definition registry must be sealed before runtime use"
            ) from exc
        except UnknownDefinitionError as exc:
            raise UnknownJobDefinitionError(
                f"runtime job is not registered: {name!r}"
            ) from exc

    def validate(self, message: JobDefinitionInput) -> None:
        if not self._registry.is_sealed:
            raise JobDefinitionRegistryUnsealedError(
                "job definition registry must be sealed before validation"
            )
        definition = self.resolve(message.name)
        definition.validate(
            producer=message.producer,
            data=message.payload,
        )

    def create(
        self,
        *,
        name: str,
        producer: str,
        job_id: str,
        resource_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> JobMessage:
        """Create one locally authorized job message."""

        if not self._registry.is_sealed:
            raise JobDefinitionRegistryUnsealedError(
                "job definition registry must be sealed before construction"
            )
        from nuself.runtime.jobs import JobMessage, JobPayload

        context = replace(current_runtime_context(), job_id=job_id)
        job_payload = JobPayload(
            resource_id=resource_id,
            data={} if payload is None else payload,
        )
        message = JobMessage(
            RuntimeEnvelope(
                kind="job",
                name=name,
                producer=producer,
                context=context,
                payload=job_payload.to_mapping(),
            )
        )
        self.validate(message)
        return message

    def seal(self) -> JobDefinitionRegistry:
        self._registry.seal()
        return self

    @property
    def definitions(self) -> tuple[RuntimeJobDefinition, ...]:
        return self._registry.definitions


def build_job_definition_registry(
    definitions: Iterable[RuntimeJobDefinition],
) -> JobDefinitionRegistry:
    """Compose domain job definitions into one sealed registry."""

    registry = JobDefinitionRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry.seal()
