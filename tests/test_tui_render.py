from __future__ import annotations

from nuself.tui.render import render_discussion_trace


def test_render_discussion_trace_formats_block() -> None:
    lines = render_discussion_trace(["host: start", "turn-1: analyst considered the idea"], title="discussion trace")

    assert lines == [
        "discussion trace:",
        "  host: start",
        "  turn-1: analyst considered the idea",
    ]
