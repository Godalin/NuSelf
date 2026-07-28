"""Shared construction helpers for framework-native agent tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from langchain_core.tools import StructuredTool

StructuredToolFactory = Callable[..., StructuredTool]


def structured_tool_factory() -> StructuredToolFactory:
    """Return the typed LangChain structured-tool factory."""
    return cast(
        StructuredToolFactory,
        StructuredTool.from_function,  # pyright: ignore[reportUnknownMemberType]
    )


def json_string_tuple_filter(
    value: list[str] | str | None,
) -> tuple[str, ...]:
    """Normalize a scalar or list filter into non-empty strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(str(item) for item in value if str(item))
