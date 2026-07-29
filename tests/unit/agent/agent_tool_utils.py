from __future__ import annotations

from langchain_core.tools import StructuredTool

from nuself.agent.tool_utils import (
    index_tool_service_components,
    tool_service_component,
)


def _lookup(query: str) -> str:
    """Look up test context."""
    return query


def test_tool_service_component_accepts_only_strings() -> None:
    valid = StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
        _lookup,
        name="valid",
        metadata={"service_component": "memory"},
    )
    missing = StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
        _lookup,
        name="missing",
    )
    invalid = StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
        _lookup,
        name="invalid",
        metadata={"service_component": 3},
    )

    assert tool_service_component(valid) == "memory"
    assert tool_service_component(missing) is None
    assert tool_service_component(invalid) is None


def test_index_tool_service_components_omits_invalid_metadata() -> None:
    valid = StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
        _lookup,
        name="valid",
        metadata={"service_component": "memory"},
    )
    invalid = StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
        _lookup,
        name="invalid",
        metadata={"service_component": object()},
    )

    assert index_tool_service_components((valid, invalid)) == {
        "valid": "memory",
    }
