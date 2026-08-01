"""macOS notification adapter using osascript."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from nuself.notification.outbox import OutboxEntry
from nuself.notification.audit import (
    report_notification_failure,
    write_notification_audit,
)


class MacOSNotificationAdapter:
    """Deliver outbox entries as macOS system notifications via osascript.

    Falls back to logging when osascript is unavailable or ``dry_run`` is set.
    """

    delivery_id = "macos"

    def __init__(self, project_root: Path | None = None, *, dry_run: bool = False) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._dry_run = dry_run
        self.has_osascript = shutil.which("osascript") is not None

    def send(self, entry: OutboxEntry) -> bool:
        if self._dry_run or not self.has_osascript:
            write_notification_audit(
                "macos_dry_run" if self._dry_run else "macos_unavailable",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": entry.attempts,
                },
            )
            return True

        script = f'display notification {self.escape(entry.body)} with title {self.escape(entry.title)}'
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
            report_notification_failure(
                TimeoutError("osascript timed out"),
                event="macos_failed",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": entry.attempts,
                },
            )
            return False
        if result.returncode != 0:
            report_notification_failure(
                RuntimeError(
                    result.stderr.strip() or "osascript failed"
                ),
                event="macos_failed",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "attempt": entry.attempts,
                },
            )
            return False
        return True

    @staticmethod
    def escape(text: str) -> str:
        return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
