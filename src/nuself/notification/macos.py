"""macOS notification adapter using osascript."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from nuself.notification import OutboxEntry
from nuself.runtime.observability import report_observed_failure


class MacOSNotificationAdapter:
    """Deliver outbox entries as macOS system notifications via osascript.

    Falls back to logging when osascript is unavailable or ``dry_run`` is set.
    """

    def __init__(self, project_root: Path | None = None, *, dry_run: bool = False) -> None:
        from nuself.config import runtime_paths
        from nuself.logs import write_log_event

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._dry_run = dry_run
        self._write_log = write_log_event
        self.has_osascript = shutil.which("osascript") is not None

    def send(self, entry: OutboxEntry) -> bool:
        if self._dry_run or not self.has_osascript:
            self._write_log(
                "outbox",
                "macos_dry_run" if self._dry_run else "macos_unavailable",
                f"{entry.title}: {entry.body}",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "idempotency_key": entry.idempotency_key,
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
            report_observed_failure(
                TimeoutError("osascript timed out"),
                component="outbox",
                event="macos_failed",
                message="macOS notification delivery failed",
                project_root=self._project_root,
                level="warning",
                status="failed",
                metadata={"entry_id": entry.id},
            )
            return False
        if result.returncode != 0:
            report_observed_failure(
                RuntimeError(
                    result.stderr.strip() or "osascript failed"
                ),
                component="outbox",
                event="macos_failed",
                message="macOS notification delivery failed",
                project_root=self._project_root,
                level="warning",
                status="failed",
                metadata={"entry_id": entry.id},
            )
            return False
        return True

    @staticmethod
    def escape(text: str) -> str:
        return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
