"""Shared daemon-status observation boundary for CLI surfaces."""

from __future__ import annotations

import sys
from pathlib import Path

from nuself.daemon import lifecycle
from nuself.runtime.diagnostics import diagnostic_exception_message


def observe_daemon_status(
    project_root: Path | None,
) -> lifecycle.DaemonStatus | None:
    """Observe daemon status and render one safe CLI failure."""

    try:
        return lifecycle.status(project_root)
    except lifecycle.DaemonStatusError as exc:
        print(
            "Daemon status unavailable: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return None
