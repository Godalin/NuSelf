"""Shared terminal workflow for compact memory previews."""

from __future__ import annotations

from pathlib import Path

from nuself.cli.application import cli_application
from nuself.tui.memory import render_memory_entry_row

DEFAULT_PREVIEW_LIMIT = 8


def format_memory_preview(
    project_root: Path | None,
    limit: int = DEFAULT_PREVIEW_LIMIT,
) -> str:
    normalized_limit = max(limit, 1)
    entries = cli_application().memory_service.list_entries()
    if not entries:
        return "No memory entries."
    shown = entries[:normalized_limit]
    lines = [render_memory_entry_row(entry) for entry in shown]
    lines.extend(("", f"  {len(shown)}/{len(entries)} entries shown."))
    if len(entries) > normalized_limit:
        lines.append(
            "  Use `nuself memory list` or "
            "`nuself memory preview --limit N` to see more."
        )
    return "\n".join(lines)
