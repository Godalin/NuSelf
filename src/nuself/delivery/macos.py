"""macOS delivery adapter using osascript."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from nuself.inbox.model import InboxItem
from nuself.delivery.audit import (
    DELIVERY_AUDIT,
)


class MacOSDeliveryAdapter:
    """Deliver Inbox items as macOS system notifications via osascript.

    Falls back to logging when osascript is unavailable or ``dry_run`` is set.
    """

    delivery_id = "macos"

    def __init__(self, project_root: Path, *, dry_run: bool = False) -> None:
        self._project_root = project_root
        self._dry_run = dry_run
        self._has_osascript = shutil.which("osascript") is not None

    def send(self, entry: InboxItem, *, attempt: int) -> bool:
        if self._dry_run or not self._has_osascript:
            DELIVERY_AUDIT.write_strict(
                "macos_dry_run" if self._dry_run else "macos_unavailable",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": attempt,
                },
            )
            return True

        script = (
            f"display notification {_escape_osascript(entry.body)} "
            f"with title {_escape_osascript(entry.title)}"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            # A hung osascript must not block the notification-delivery thread.
            DELIVERY_AUDIT.failure(
                TimeoutError("osascript timed out"),
                event="macos_failed",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": attempt,
                },
            )
            return False
        if result.returncode != 0:
            DELIVERY_AUDIT.failure(
                RuntimeError(
                    result.stderr.strip() or "osascript failed"
                ),
                event="macos_failed",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": attempt,
                },
            )
            return False
        return True



def _escape_osascript(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
