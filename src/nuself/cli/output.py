"""Shared output and visible-handle helpers for terminal adapters."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from typing import Any

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI

from nuself.runtime.handles import (
    VisibleHandleError,
    resolve_visible_handle,
    resolve_visible_handle_selection,
)
from nuself.runtime.diagnostics import diagnostic_exception_message

def print_ansi(text: str, **kwargs: Any) -> None:
    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        print_formatted_text(ANSI(text), **kwargs)
    else:
        print(text, **kwargs)


def print_json_lines(*entities: object) -> None:
    """Print machine-readable entities using the shared CLI JSONL contract."""

    for entity in entities:
        print(json.dumps(entity, sort_keys=True, ensure_ascii=True))


def resolve_handle[_HandleItem](
    value: str,
    items: Sequence[_HandleItem],
    *,
    label: str,
    get_id: Callable[[_HandleItem], str],
) -> str | None:
    try:
        return resolve_visible_handle(value, items, label=label, get_id=get_id)
    except VisibleHandleError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return None


def resolve_handle_selection[_HandleItem](
    value: str,
    items: Sequence[_HandleItem],
    *,
    label: str,
    get_id: Callable[[_HandleItem], str],
) -> list[str] | None:
    try:
        return resolve_visible_handle_selection(
            value, items, label=label, get_id=get_id
        )
    except VisibleHandleError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return None
