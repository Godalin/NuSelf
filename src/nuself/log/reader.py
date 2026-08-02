"""Structured log reading and incremental interactive cursors."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import cast

from nuself.log.record import LogEvent
from nuself.log.store import component_log_paths, log_path
from nuself.log.warning import LOG_TERMINAL_WARNING_REGISTRY
from nuself.runtime.audit.types import LOG_COMPONENTS, LogComponent
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.warning_definitions import emit_registered_terminal_warning


def read_log_events(
    *,
    project_root: Path | None = None,
    component: LogComponent | None = None,
    tail: int | None = None,
) -> list[LogEvent]:
    """Read structured events from local logs, tolerating legacy plain lines."""

    events: list[LogEvent] = []
    components: Iterable[LogComponent] = (
        (component,) if component is not None else LOG_COMPONENTS
    )
    for current_component in components:
        active_path = log_path(current_component, project_root=project_root)
        for path in component_log_paths(active_path):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                continue
            corruptions: list[Exception] = []
            for line in lines:
                parsed = _parse_log_line(
                    line,
                    current_component,
                    on_corrupt=corruptions.append,
                )
                if parsed is not None:
                    events.append(parsed)
            _report_log_read_corruptions(
                path,
                current_component,
                corruptions,
            )
    events.sort(key=_log_event_chronological_key)
    events, identity_conflicts = _reconcile_log_event_identities(
        events,
        seen_event_keys=set(),
        seen_event_fingerprints={},
    )
    _report_log_identity_conflicts(identity_conflicts)
    if tail is not None and tail > 0:
        return events[-tail:]
    return events


def _parse_log_line(
    line: str,
    component: LogComponent,
    *,
    on_corrupt: Callable[[Exception], None] | None = None,
) -> LogEvent | None:
    stripped = line.strip()
    if stripped == "":
        return None
    try:
        parsed: object = json.loads(stripped)
    except json.JSONDecodeError:
        return LogEvent(
            time="",
            level="info",
            component=component,
            event="legacy",
            message=stripped,
            event_id=None,
            schema_version=None,
            _allow_empty_time=True,
        )
    if not isinstance(parsed, dict):
        if on_corrupt is not None:
            on_corrupt(
                ValueError("structured log record must be a JSON object")
            )
        return None
    try:
        return LogEvent.from_record(cast(dict[str, object], parsed))
    except (TypeError, ValueError) as exc:
        if on_corrupt is not None:
            on_corrupt(exc)
        return None


def _report_log_read_corruptions(
    path: Path,
    component: LogComponent,
    corruptions: list[Exception],
) -> None:
    if not corruptions:
        return
    first = corruptions[0]
    detail = diagnostic_exception_message(first)
    emit_registered_terminal_warning(
        LOG_TERMINAL_WARNING_REGISTRY,
        "logs/corrupt_records_skipped",
        {
            "component": component,
            "file": path.name,
            "count": len(corruptions),
            "first_error": f"{type(first).__name__}: {detail}",
        },
        stacklevel=3,
    )


def _log_event_chronological_key(
    event: LogEvent,
) -> tuple[int, datetime]:
    return event.chronological_key()


# ============================================================================
# Read-side utilities
# ============================================================================


def _log_event_fingerprint(event: LogEvent) -> str:
    return json.dumps(
        event.to_record(),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _reconcile_log_event_identities(
    events: Iterable[LogEvent],
    *,
    seen_event_keys: set[str],
    seen_event_fingerprints: dict[str, str],
) -> tuple[list[LogEvent], list[LogEvent]]:
    canonical: list[LogEvent] = []
    conflicts: list[LogEvent] = []
    for event in events:
        if event.event_id is not None:
            key = f"id:{event.event_id}"
        else:
            record = event.to_record()
            record.pop("event_id", None)
            record.pop("schema_version", None)
            key = (
                "legacy:"
                f"{json.dumps(record, sort_keys=True, ensure_ascii=True)}"
            )
        fingerprint = _log_event_fingerprint(event)
        if key not in seen_event_keys:
            seen_event_keys.add(key)
            seen_event_fingerprints[key] = fingerprint
            canonical.append(event)
            continue
        existing = seen_event_fingerprints.get(key)
        if existing is None:
            seen_event_fingerprints[key] = fingerprint
            continue
        if existing != fingerprint:
            conflicts.append(event)
    return canonical, conflicts


def _report_log_identity_conflicts(
    conflicts: list[LogEvent],
) -> None:
    if not conflicts:
        return
    first = conflicts[0]
    emit_registered_terminal_warning(
        LOG_TERMINAL_WARNING_REGISTRY,
        "logs/event_identity_conflict",
        {
            "count": len(conflicts),
            "first_component": first.component,
            "first_event": first.event,
        },
        stacklevel=3,
    )


class InteractiveLogCursor:
    """Incrementally reads complete lines appended after cursor creation."""

    def __init__(
        self,
        seen_event_keys: set[str] | None = None,
        seen_event_fingerprints: dict[str, str] | None = None,
        offsets: dict[LogComponent, int] | None = None,
        identities: dict[LogComponent, tuple[int, int] | None] | None = None,
    ) -> None:
        self.seen_event_keys: set[str] = (
            seen_event_keys if seen_event_keys is not None else set()
        )
        self.seen_event_fingerprints: dict[str, str] = (
            seen_event_fingerprints
            if seen_event_fingerprints is not None
            else {}
        )
        self.offsets = offsets if offsets is not None else {}
        self.identities = identities if identities is not None else {}

    @classmethod
    def from_project(cls, project_root: Path | None) -> InteractiveLogCursor:
        offsets: dict[LogComponent, int] = {}
        identities: dict[LogComponent, tuple[int, int] | None] = {}
        for component in LOG_COMPONENTS:
            path = log_path(component, project_root=project_root)
            try:
                stat = path.stat()
                offsets[component] = stat.st_size
                identities[component] = (stat.st_dev, stat.st_ino)
            except FileNotFoundError:
                offsets[component] = 0
                identities[component] = None
        return cls(offsets=offsets, identities=identities)

    def mark_seen(self, events: Iterable[LogEvent]) -> None:
        """Register events delivered through a non-file transport."""

        _, conflicts = _reconcile_log_event_identities(
            events,
            seen_event_keys=self.seen_event_keys,
            seen_event_fingerprints=self.seen_event_fingerprints,
        )
        _report_log_identity_conflicts(conflicts)

    def read_new_events(self, project_root: Path | None) -> list[LogEvent]:
        events: list[LogEvent] = []
        for component in LOG_COMPONENTS:
            events.extend(self._read_component(component, project_root))
        events.sort(key=_log_event_chronological_key)
        new_events, conflicts = _reconcile_log_event_identities(
            events,
            seen_event_keys=self.seen_event_keys,
            seen_event_fingerprints=self.seen_event_fingerprints,
        )
        _report_log_identity_conflicts(conflicts)
        return new_events

    def _read_component(
        self,
        component: LogComponent,
        project_root: Path | None,
    ) -> list[LogEvent]:
        path = log_path(component, project_root=project_root)
        offset = self.offsets.get(component, 0)
        previous_identity = self.identities.get(component)
        try:
            stat = path.stat()
        except FileNotFoundError:
            self.offsets[component] = 0
            self.identities[component] = None
            return []
        current_identity = (stat.st_dev, stat.st_ino)
        parsed_events: list[LogEvent] = []
        if previous_identity is not None and previous_identity != current_identity:
            rotated_path = _find_log_with_identity(
                path,
                previous_identity,
            )
            if rotated_path is not None:
                rotated_events, _ = _read_log_path(
                    rotated_path,
                    component=component,
                    offset=offset,
                )
                parsed_events.extend(rotated_events)
            offset = 0
        elif stat.st_size < offset:
            offset = 0
        current_events, next_offset = _read_log_path(
            path,
            component=component,
            offset=offset,
        )
        parsed_events.extend(current_events)
        self.offsets[component] = next_offset
        self.identities[component] = current_identity
        return parsed_events


def _find_log_with_identity(
    active_path: Path,
    identity: tuple[int, int],
) -> Path | None:
    for candidate in component_log_paths(active_path):
        if candidate == active_path:
            continue
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            continue
        if (stat.st_dev, stat.st_ino) == identity:
            return candidate
    return None


def _read_log_path(
    path: Path,
    *,
    component: LogComponent,
    offset: int,
) -> tuple[list[LogEvent], int]:
    with path.open("rb") as log_file:
        log_file.seek(offset)
        appended = log_file.read()
    complete_length = _complete_line_length(appended)
    parsed_events: list[LogEvent] = []
    corruptions: list[Exception] = []
    for raw_line in appended[:complete_length].splitlines():
        line = raw_line.decode("utf-8", errors="replace")
        parsed = _parse_log_line(
            line,
            component,
            on_corrupt=corruptions.append,
        )
        if parsed is not None:
            parsed_events.append(parsed)
    _report_log_read_corruptions(path, component, corruptions)
    return parsed_events, offset + complete_length


def _complete_line_length(content: bytes) -> int:
    """Return the byte boundary after the last complete newline."""

    last_newline = content.rfind(b"\n")
    return last_newline + 1 if last_newline >= 0 else 0
