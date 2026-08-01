from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from nuself.runtime.context import RuntimeContext
from nuself.runtime.job_definitions import (
    DuplicateJobDefinitionError,
    JobDefinitionRegistry,
    JobDefinitionRegistrySealedError,
    JobDefinitionRegistryUnsealedError,
    RuntimeJobDefinition,
    UnknownJobDefinitionError,
    build_job_definition_registry,
)
from nuself.runtime.jobs import JobMessage
from nuself.runtime.messages import RuntimeEnvelope


def _definition() -> RuntimeJobDefinition:
    def validate(producer: str, data: Mapping[str, object]) -> None:
        assert producer == "producer"
        if set(data) != {"value"}:
            raise ValueError("invalid data")

    return RuntimeJobDefinition(
        name="example.job",
        description="An example typed job.",
        producers=frozenset({"producer"}),
        data_validator=validate,
    )


def _message(
    *,
    name: str = "example.job",
    producer: str = "producer",
    payload: Mapping[str, object] | None = None,
) -> JobMessage:
    return JobMessage(
        RuntimeEnvelope(
            kind="job",
            name=name,
            producer=producer,
            context=RuntimeContext(job_id="job-1"),
            payload={
                "resource_id": "resource-1",
                "data": {"value": 1} if payload is None else payload,
            },
        )
    )


def test_job_definition_registry_validates_typed_message() -> None:
    registry = build_job_definition_registry((_definition(),))

    registry.validate(_message())


def test_job_definition_registry_creates_only_valid_messages() -> None:
    registry = build_job_definition_registry((_definition(),))

    message = registry.create(
        name="example.job",
        producer="producer",
        job_id="job-1",
        resource_id="resource-1",
        payload={"value": 1},
    )

    assert message.name == "example.job"
    assert message.producer == "producer"
    assert message.job_id == "job-1"
    assert message.resource_id == "resource-1"
    assert message.payload == {"value": 1}


def test_job_definition_registry_rejects_create_before_sealing() -> None:
    registry = JobDefinitionRegistry().register(_definition())

    with pytest.raises(JobDefinitionRegistryUnsealedError):
        registry.resolve("example.job")
    with pytest.raises(JobDefinitionRegistryUnsealedError):
        registry.validate(_message())
    with pytest.raises(JobDefinitionRegistryUnsealedError):
        registry.create(
            name="example.job",
            producer="producer",
            job_id="job-1",
            resource_id="resource-1",
            payload={"value": 1},
        )


@pytest.mark.parametrize(
    ("name", "producer", "payload"),
    (
        ("unknown.job", "producer", {"value": 1}),
        ("example.job", "other", {"value": 1}),
        ("example.job", "producer", {"other": 1}),
    ),
)
def test_job_definition_registry_rejects_invalid_message_during_create(
    name: str,
    producer: str,
    payload: Mapping[str, object],
) -> None:
    registry = build_job_definition_registry((_definition(),))

    with pytest.raises((UnknownJobDefinitionError, ValueError)):
        registry.create(
            name=name,
            producer=producer,
            job_id="job-1",
            resource_id="resource-1",
            payload=payload,
        )


def test_job_definition_registry_rejects_unknown_job() -> None:
    registry = build_job_definition_registry((_definition(),))

    with pytest.raises(UnknownJobDefinitionError):
        registry.validate(_message(name="unknown.job"))


def test_job_definition_rejects_disallowed_producer_and_data() -> None:
    registry = build_job_definition_registry((_definition(),))

    with pytest.raises(ValueError, match="producer"):
        registry.validate(_message(producer="other"))
    with pytest.raises(ValueError, match="invalid data"):
        registry.validate(_message(payload={"other": 1}))


def test_job_definition_registry_rejects_duplicate_and_late_registration() -> None:
    registry = JobDefinitionRegistry().register(_definition())

    with pytest.raises(DuplicateJobDefinitionError):
        registry.register(_definition())

    registry.seal()
    with pytest.raises(JobDefinitionRegistrySealedError):
        registry.register(
            RuntimeJobDefinition(
                name="other.job",
                description="Another job.",
                producers=frozenset({"producer"}),
            )
        )


@pytest.mark.parametrize(
    ("name", "producers"),
    (
        ("invalid", frozenset({"producer"})),
        ("valid.job", frozenset[str]()),
        ("valid.job", frozenset({"invalid.producer"})),
    ),
)
def test_job_definition_rejects_invalid_identity_or_empty_producers(
    name: str,
    producers: frozenset[str],
) -> None:
    with pytest.raises(ValueError):
        RuntimeJobDefinition(
            name=name,
            description="Invalid definition.",
            producers=producers,
        )


def test_job_definition_rejects_non_callable_validator() -> None:
    with pytest.raises(TypeError, match="validator"):
        RuntimeJobDefinition(
            name="valid.job",
            description="Invalid definition.",
            producers=frozenset({"producer"}),
            data_validator=cast(object, "not callable"),  # type: ignore[arg-type]
        )
