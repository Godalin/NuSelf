from __future__ import annotations

from dataclasses import dataclass

import pytest

from nuself.runtime.definitions import (
    DefinitionRegistry,
    DefinitionRegistrySealedError,
    DefinitionRegistryUnsealedError,
    DuplicateDefinitionError,
    UnknownDefinitionError,
)


@dataclass(frozen=True)
class _Definition:
    name: str
    value: int


def test_definition_registry_preserves_order_and_resolves_keys() -> None:
    first = _Definition("first", 1)
    second = _Definition("second", 2)
    registry = DefinitionRegistry[str, _Definition](
        lambda definition: definition.name,
        namespace="test",
    )

    returned = registry.register(first).register(second).seal()

    assert returned is registry
    assert registry.resolve("first") is first
    assert registry.resolve("second") is second
    assert registry.definitions == (first, second)


def test_definition_registry_rejects_duplicate_keys() -> None:
    registry = DefinitionRegistry[str, _Definition](
        lambda definition: definition.name,
        namespace="test",
    )
    registry.register(_Definition("same", 1))

    with pytest.raises(DuplicateDefinitionError) as captured:
        registry.register(_Definition("same", 2))

    assert captured.value.namespace == "test"
    assert captured.value.key == "same"


def test_definition_registry_rejects_unknown_keys() -> None:
    registry = DefinitionRegistry[str, _Definition](
        lambda definition: definition.name,
        namespace="test",
    ).seal()

    with pytest.raises(UnknownDefinitionError) as captured:
        registry.resolve("missing")

    assert captured.value.namespace == "test"
    assert captured.value.key == "missing"


def test_definition_registry_can_store_none_as_a_definition() -> None:
    registry = DefinitionRegistry[str, None](
        lambda definition: "none",
        namespace="test",
    ).register(None).seal()

    assert registry.resolve("none") is None


def test_definition_registry_rejects_lookup_before_seal() -> None:
    registry = DefinitionRegistry[str, _Definition](
        lambda definition: definition.name,
        namespace="test",
    ).register(_Definition("first", 1))

    with pytest.raises(DefinitionRegistryUnsealedError) as captured:
        registry.resolve("first")

    assert captured.value.namespace == "test"
    assert registry.definitions == (_Definition("first", 1),)


def test_definition_registry_rejects_registration_after_seal() -> None:
    registry = DefinitionRegistry[str, _Definition](
        lambda definition: definition.name,
        namespace="test",
    ).seal()

    with pytest.raises(DefinitionRegistrySealedError) as captured:
        registry.register(_Definition("late", 1))

    assert captured.value.namespace == "test"


def test_definition_registry_snapshots_do_not_change_retroactively() -> None:
    registry = DefinitionRegistry[str, _Definition](
        lambda definition: definition.name,
        namespace="test",
    )
    registry.register(_Definition("first", 1))
    snapshot = registry.definitions

    registry.register(_Definition("second", 2))

    assert tuple(definition.name for definition in snapshot) == ("first",)
    assert tuple(
        definition.name for definition in registry.definitions
    ) == ("first", "second")


def test_definition_registry_rejects_non_callable_key_function() -> None:
    with pytest.raises(TypeError):
        DefinitionRegistry[str, _Definition](
            object(),  # type: ignore[arg-type]
            namespace="test",
        )


def test_definition_registry_rejects_empty_namespace() -> None:
    with pytest.raises(ValueError):
        DefinitionRegistry[str, _Definition](
            lambda definition: definition.name,
            namespace="",
        )
