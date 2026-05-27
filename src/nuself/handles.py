"""Shared visible-index handle parsing for CLI-like object commands."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import re
from typing import TypeVar

T = TypeVar("T")

_INDEX_SELECTION_RE = re.compile(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*")


class VisibleHandleError(ValueError):
    """Raised when a visible index or compact index selection is invalid."""


def looks_like_visible_index(value: str) -> bool:
    return value.isdigit()


def uses_visible_selection_syntax(value: str) -> bool:
    return "," in value or looks_like_visible_index_range(value)


def looks_like_visible_index_range(value: str) -> bool:
    """Return true when a value is trying to use the visible range syntax."""

    return value[:1].isdigit() and "-" in value


def parse_visible_index(value: str, *, count: int, label: str) -> int:
    try:
        index = int(value)
    except ValueError as exc:
        raise VisibleHandleError(f"Invalid {label} index: {value}") from exc
    if index < 0 or index >= count:
        valid = f"0-{count - 1}" if count else "(none)"
        raise VisibleHandleError(f"Invalid {label} index {index}. Valid range: {valid}")
    return index


def parse_visible_index_selection(value: str, *, count: int, label: str) -> list[int]:
    """Parse a compact 0-based index selection such as `1,3-5,9`."""

    if _INDEX_SELECTION_RE.fullmatch(value) is None:
        raise VisibleHandleError(
            f"Invalid {label} index selection: {value}. Expected compact form like 0,2-4,8."
        )
    indexes: list[int] = []
    seen: set[int] = set()
    for token in value.split(","):
        if "-" in token:
            start_raw, end_raw = token.split("-", maxsplit=1)
            start = int(start_raw)
            end = int(end_raw)
            if start > end:
                raise VisibleHandleError(f"Invalid {label} index range {token}. Range start must be <= end.")
            expanded = range(start, end + 1)
        else:
            expanded = range(int(token), int(token) + 1)
        for index in expanded:
            if index < 0 or index >= count:
                valid = f"0-{count - 1}" if count else "(none)"
                raise VisibleHandleError(f"Invalid {label} index {index}. Valid range: {valid}")
            if index not in seen:
                indexes.append(index)
                seen.add(index)
    return indexes


def resolve_visible_item(value: str, items: Sequence[T], *, label: str) -> T | None:
    """Resolve a numeric visible index to an item; nonnumeric values return None."""

    if not looks_like_visible_index(value):
        return None
    return items[parse_visible_index(value, count=len(items), label=label)]


def resolve_visible_handle(
    value: str,
    items: Sequence[T],
    *,
    label: str,
    get_id: Callable[[T], str],
) -> str:
    """Resolve a numeric visible index to an id, otherwise return the stable id value."""

    item = resolve_visible_item(value, items, label=label)
    if item is None:
        return value
    return get_id(item)


def resolve_visible_handle_selection(
    value: str,
    items: Sequence[T],
    *,
    label: str,
    get_id: Callable[[T], str],
) -> list[str]:
    """Resolve one id/index or a compact index selection into stable ids."""

    if not looks_like_visible_index(value) and not uses_visible_selection_syntax(value):
        return [value]
    if looks_like_visible_index(value):
        return [get_id(items[parse_visible_index(value, count=len(items), label=label)])]
    indexes = parse_visible_index_selection(value, count=len(items), label=label)
    return [get_id(items[index]) for index in indexes]
