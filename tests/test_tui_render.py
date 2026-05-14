from __future__ import annotations

from nuself.logs import LogEvent
from nuself.tui.render import render_discussion_trace, render_host_decision, render_log_event


def test_render_discussion_trace_formats_block() -> None:
    lines = render_discussion_trace(["host: start", "turn-1:analyst: considered the idea"], title="discussion trace")

    assert lines == [
        "discussion trace:",
        "  ── host ──",
        "    [host]             start",
        "",
        "  ── turn-1 ──",
        "    [analyst]          considered the idea",
    ]


def test_render_host_decision_formats_block() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="persona",
        event="host_discussion_decision",
        message="user asked for multi-perspective discussion",
        thread_id="default",
        status="approved",
        metadata={"should_escalate": True, "escalation_reason": "multi-perspective request"},
    )

    lines = render_host_decision(event)

    assert lines == [
        '[host decision] host_discussion_decision user asked for multi-perspective discussion status=approved thread=default escalation_reason="multi-perspective request" should_escalate=true',
    ]


def test_render_persona_summary_formats_personas_on_separate_lines() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="persona",
        event="persona_summary",
        message=(
            "analyst_self: Analyst decomposes the question.\n"
            "skeptic_self: Skeptic challenges the assumption.\n"
            "synthesizer_self: Synthesis keeps the useful tension."
        ),
        thread_id="default",
        status="deep tradeoff",
        metadata={"persona_count": 2, "has_synthesis": True},
    )

    assert render_log_event(event, color=False).splitlines() == [
        '[selves] persona_summary status="deep tradeoff" thread=default has_synthesis=true persona_count=2',
        "  analyst_self: Analyst decomposes the question.",
        "  skeptic_self: Skeptic challenges the assumption.",
        "  synthesizer_self: Synthesis keeps the useful tension.",
    ]


def test_render_persona_summary_colors_each_self_label() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="persona",
        event="persona_summary",
        message=(
            "analyst_self: Analyst decomposes the question.\n"
            "skeptic_self: Skeptic challenges the assumption.\n"
            "builder_self: Builder proposes the next move."
        ),
        thread_id="default",
        status="deep tradeoff",
        metadata={"persona_count": 3, "has_synthesis": False},
    )

    lines = render_log_event(event, color=True).splitlines()

    assert lines[1] == "  \033[36manalyst_self\033[0m: Analyst decomposes the question."
    assert lines[2] == "  \033[31mskeptic_self\033[0m: Skeptic challenges the assumption."
    assert lines[3] == "  \033[32mbuilder_self\033[0m: Builder proposes the next move."
