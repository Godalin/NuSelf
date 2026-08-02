from __future__ import annotations

import warnings

import pytest

from nuself.runtime.definitions import (
    DefinitionRegistrySealedError,
    DuplicateDefinitionError,
    UnknownDefinitionError,
)
from nuself.runtime.warning import (
    TerminalWarningDefinition,
    TerminalWarningRegistry,
    TerminalWarningRegistryUnsealedError,
    TerminalWarningSchemaError,
    emit_registered_terminal_warning,
)


def _registry() -> TerminalWarningRegistry:
    return (
        TerminalWarningRegistry()
        .register(
            TerminalWarningDefinition(
                "test/failed",
                ("stage", "count"),
                lambda metadata: None,
                suffix="continuing safely",
            )
        )
        .seal()
    )


def test_terminal_warning_registry_is_duplicate_safe_and_sealed() -> None:
    definition = TerminalWarningDefinition("test/failed", ())
    registry = TerminalWarningRegistry().register(definition)

    with pytest.raises(DuplicateDefinitionError):
        registry.register(definition)

    registry.seal()
    with pytest.raises(DefinitionRegistrySealedError):
        registry.register(
            TerminalWarningDefinition("test/other_failed", ())
        )
    with pytest.raises(UnknownDefinitionError):
        registry.resolve("test/unknown")


def test_terminal_warning_registry_rejects_lookup_before_seal() -> None:
    registry = TerminalWarningRegistry().register(
        TerminalWarningDefinition("test/failed", ())
    )

    with pytest.raises(TerminalWarningRegistryUnsealedError):
        registry.resolve("test/failed")


def test_terminal_warning_render_is_exact_ordered_and_redacted() -> None:
    definition = _registry().resolve("test/failed")

    rendered = definition.render(
        {
            "count": 2,
            "stage": "api_key=provider-secret",
        }
    )

    assert rendered == (
        "test/failed: stage=api_key=*** count=2; continuing safely"
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {"stage": "read"},
        {"stage": "read", "count": 1, "extra": True},
        {"stage": " ", "count": 1},
        {"stage": "read", "count": True},
    ],
)
def test_terminal_warning_render_rejects_invalid_shape_or_values(
    metadata: dict[str, object],
) -> None:
    with pytest.raises(TerminalWarningSchemaError):
        _registry().resolve("test/failed").render(metadata)


def test_registered_terminal_warning_render_failure_is_non_raising() -> None:
    registry = _registry()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        emit_registered_terminal_warning(
            registry,
            "test/failed",
            {"stage": "read"},
            stacklevel=1,
        )

    assert len(captured) == 1
    assert str(captured[0].message).startswith(
        "runtime/terminal_warning_render_failed: event=test/failed error="
    )
