"""Shared presentation effects for one interactive REPL session."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nuself.cli.output import print_ansi
from nuself.tui.render import render_session_header

DaemonStatusProvider = Callable[[Path | None], str]


@dataclass(frozen=True)
class SessionHeaderPresenter:
    """Render every session header through one injected status provider."""

    daemon_status: DaemonStatusProvider

    def show(
        self,
        project_root: Path | None,
        conversation_id: str,
    ) -> None:
        print_ansi(
            render_session_header(
                daemon_status=self.daemon_status(project_root),
                conversation_id=conversation_id,
            )
        )
