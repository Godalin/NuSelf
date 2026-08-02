"""Actionable, payload-safe notices for interactive chat."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nuself.cli.composition import compose_cli_application
from nuself.logs import read_log_events
from nuself.runtime.log_event import LogEvent

_REPAIRABLE_COLLECTION_ALIASES = {
    "conversations": "conversations",
    "memory_entries": "memory",
}


@dataclass(frozen=True)
class InteractiveNotice:
    """One concise condition that deserves a user's attention."""

    code: str
    message: str


def startup_interactive_notices(
    project_root: Path | None,
    *,
    cwd: Path | None = None,
) -> tuple[InteractiveNotice, ...]:
    """Project selected authority state and recent failures for REPL startup."""

    authority_root = (
        project_root.absolute()
        if project_root is not None
        else None
    )
    notices: list[InteractiveNotice] = []
    config = compose_cli_application(project_root).config
    if not any(
        endpoint.api_key.strip()
        and endpoint.base_url.strip()
        and endpoint.model.strip()
        for endpoint in config.llm.endpoints
    ):
        location = (
            str(authority_root / "config.yaml")
            if authority_root is not None
            else "the selected authority config"
        )
        notices.append(
            InteractiveNotice(
                "model-unconfigured",
                f"No usable model endpoint is configured in {location}; "
                "chat cannot produce a model-backed reply.",
            )
        )

    current = (cwd or Path.cwd()).absolute()
    local_authority = current / ".nuself"
    if (
        authority_root is not None
        and local_authority.is_dir()
        and authority_root != local_authority
    ):
        notices.append(
            InteractiveNotice(
                "workspace-authority-not-selected",
                f"This session uses {authority_root}, but {local_authority} "
                "also exists; restart with `nuself --local` to use it.",
            )
        )

    try:
        recent = read_log_events(project_root=project_root, tail=500)
    except OSError:
        recent = []
    notices.extend(_recent_failure_notices(recent))
    return tuple(notices)


def turn_interactive_notices(
    events: list[LogEvent],
) -> tuple[InteractiveNotice, ...]:
    """Aggregate hidden record failures emitted during one chat turn."""

    failed = [
        event for event in events if event.event == "record_decode_failed"
    ]
    counts = Counter(event.component for event in failed)
    return tuple(
        InteractiveNotice(
            f"{component}-records-unreadable",
            f"{count} {component} record(s) could not be read; this reply may "
            f"lack context. {_record_recovery_instruction(failed, component)}",
        )
        for component, count in sorted(counts.items())
    )


def _recent_failure_notices(
    events: list[LogEvent],
) -> tuple[InteractiveNotice, ...]:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    recent_events = [
        event for event in events if _event_at_or_after(event, cutoff)
    ]
    failed = _unresolved_record_failures(
        [
            event
            for event in recent_events
            if event.event == "record_decode_failed"
        ],
        recent_events,
    )
    record_counts = Counter(event.component for event in failed)
    notices = [
        InteractiveNotice(
            f"recent-{component}-records-unreadable",
            f"Recent logs contain {count} {component} record decode failure(s); "
            f"{_record_recovery_instruction(failed, component)}",
        )
        for component, count in sorted(record_counts.items())
    ]
    delivery_count = sum(
        event.event == "response_delivery_failed"
        for event in recent_events
    )
    if delivery_count:
        notices.append(
            InteractiveNotice(
                "recent-response-delivery-failed",
                f"The daemon recently failed to deliver {delivery_count} "
                "completed response(s), usually because a client disconnected. "
                "Chat replies remain in `:history`; if this recurs, run "
                "`nuself daemon restart`.",
            )
        )
    return tuple(notices)


def _unresolved_record_failures(
    failures: list[LogEvent],
    events: list[LogEvent],
) -> list[LogEvent]:
    repaired_at: dict[tuple[str, str], datetime] = {}
    for event in events:
        if (
            event.event != "data_record_updated"
            or event.metadata is None
        ):
            continue
        collection = event.metadata.get("collection")
        record_id = event.metadata.get("record_id")
        instant = _event_instant(event)
        if (
            not isinstance(collection, str)
            or not isinstance(record_id, str)
            or instant is None
        ):
            continue
        identity = (collection, record_id)
        previous = repaired_at.get(identity)
        if previous is None or instant > previous:
            repaired_at[identity] = instant

    unresolved: list[LogEvent] = []
    for failure in failures:
        if failure.metadata is None:
            unresolved.append(failure)
            continue
        collection = failure.metadata.get("collection")
        record_id = failure.metadata.get("record_id")
        failed_at = _event_instant(failure)
        if (
            not isinstance(collection, str)
            or not isinstance(record_id, str)
            or failed_at is None
        ):
            unresolved.append(failure)
            continue
        repaired = repaired_at.get((collection, record_id))
        if repaired is None or repaired <= failed_at:
            unresolved.append(failure)
    return unresolved


def _record_recovery_instruction(
    events: list[LogEvent],
    component: str,
) -> str:
    collections: set[str] = set()
    for event in events:
        if event.component != component or event.metadata is None:
            continue
        collection = event.metadata.get("collection")
        if isinstance(collection, str):
            collections.add(collection)
    if len(collections) == 1:
        collection = next(iter(collections))
        alias = _REPAIRABLE_COLLECTION_ALIASES.get(collection)
        if alias is not None:
            return f"Check and repair with `nuself data check {alias}`."
    return f"Inspect with `nuself dev logs --component {component}`."


def _event_at_or_after(event: LogEvent, cutoff: datetime) -> bool:
    instant = _event_instant(event)
    return instant is not None and instant >= cutoff


def _event_instant(event: LogEvent) -> datetime | None:
    try:
        instant = datetime.fromisoformat(event.time)
    except ValueError:
        return None
    if instant.tzinfo is None:
        return None
    return instant.astimezone(UTC)


def print_interactive_notices(
    notices: tuple[InteractiveNotice, ...],
) -> None:
    """Render one grouped notice block."""

    if not notices:
        return
    print()
    print("Attention:")
    for notice in notices:
        print(f"  ! {notice.message}")
