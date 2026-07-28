"""Shared lexical contracts for runtime and persisted event identities."""

from __future__ import annotations

import re

_IDENTITY_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")


def require_identity_segment(value: object, *, label: str) -> str:
    """Return one valid lowercase identity segment or raise."""

    if not isinstance(value, str) or _IDENTITY_SEGMENT.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def require_runtime_event_name(value: object) -> str:
    """Return a dotted runtime event name with at least two segments."""

    if not isinstance(value, str):
        raise ValueError("runtime event name is invalid")
    segments = value.split(".")
    if len(segments) < 2 or any(
        _IDENTITY_SEGMENT.fullmatch(segment) is None
        for segment in segments
    ):
        raise ValueError("runtime event name is invalid")
    return value


def require_audit_event_name(value: object) -> str:
    """Return one direct persisted audit slug."""

    return require_identity_segment(value, label="audit event name")


def require_persisted_event_name(value: object) -> str:
    """Return a current audit slug or registered-event projection name."""

    if isinstance(value, str) and "." in value:
        return require_runtime_event_name(value)
    return require_audit_event_name(value)
