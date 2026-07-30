"""Actionable, payload-safe notices for interactive chat."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nuself.config import ConfigSystem
from nuself.logs import LogEvent, read_log_events


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
    try:
        config = ConfigSystem.load(project_root=project_root)
    except (OSError, ValueError):
        config = None
        notices.append(
            InteractiveNotice(
                "configuration-invalid",
                "The selected authority configuration is invalid or unreadable; "
                "run `nuself dev config` to inspect it.",
            )
        )
    if config is not None and not any(
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

    counts = Counter(
        event.component
        for event in events
        if event.event == "record_decode_failed"
    )
    return tuple(
        InteractiveNotice(
            f"{component}-records-unreadable",
            f"{count} {component} record(s) could not be read; this reply may "
            f"lack context. Inspect with `nuself dev logs --component {component}`.",
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
    record_counts = Counter(
        event.component
        for event in recent_events
        if event.event == "record_decode_failed"
    )
    notices = [
        InteractiveNotice(
            f"recent-{component}-records-unreadable",
            f"Recent logs contain {count} unreadable {component} record(s); "
            f"inspect with `nuself dev logs --component {component}`.",
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
                "completed response(s), usually because a client disconnected; "
                "inspect with `nuself dev logs --component daemon`.",
            )
        )
    return tuple(notices)


def _event_at_or_after(event: LogEvent, cutoff: datetime) -> bool:
    try:
        instant = datetime.fromisoformat(event.time)
    except ValueError:
        return False
    if instant.tzinfo is None:
        return False
    return instant.astimezone(UTC) >= cutoff


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
