from __future__ import annotations

import pytest

from nuself.handles import (
    VisibleHandleError,
    parse_visible_index_selection,
    resolve_visible_handle,
    resolve_visible_handle_selection,
)


class Item:
    def __init__(self, item_id: str) -> None:
        self.id = item_id


def test_resolve_visible_handle_uses_numeric_index() -> None:
    items = [Item("a"), Item("b")]

    assert resolve_visible_handle("1", items, label="item", get_id=lambda item: item.id) == "b"


def test_resolve_visible_handle_keeps_stable_id() -> None:
    items = [Item("a")]

    assert resolve_visible_handle("custom-id", items, label="item", get_id=lambda item: item.id) == "custom-id"


def test_resolve_visible_handle_selection_expands_ranges_and_deduplicates() -> None:
    items = [Item("a"), Item("b"), Item("c"), Item("d")]

    assert resolve_visible_handle_selection("0,2-3,2", items, label="item", get_id=lambda item: item.id) == [
        "a",
        "c",
        "d",
    ]


def test_resolve_visible_handle_selection_uses_single_numeric_index() -> None:
    items = [Item("a"), Item("b")]

    assert resolve_visible_handle_selection("1", items, label="item", get_id=lambda item: item.id) == ["b"]


def test_resolve_visible_handle_selection_keeps_hyphenated_stable_id() -> None:
    items = [Item("a")]

    assert resolve_visible_handle_selection("reflection-candidate-1", items, label="item", get_id=lambda item: item.id) == [
        "reflection-candidate-1",
    ]


def test_parse_visible_index_selection_rejects_whitespace() -> None:
    with pytest.raises(VisibleHandleError, match="Invalid item index selection"):
        parse_visible_index_selection("0, 1", count=2, label="item")


def test_parse_visible_index_selection_rejects_reversed_range() -> None:
    with pytest.raises(VisibleHandleError, match="Range start must be <= end"):
        parse_visible_index_selection("2-1", count=3, label="item")
