from __future__ import annotations

from nuself.logs import LogEvent
from nuself.notification import OutboxEntry
from nuself.reflection.repository import ReflectionEntry
from nuself.tui.render import (
    format_display_timestamp,
    render_discussion_trace,
    render_host_decision,
    render_log_event,
    render_outbox_detail,
    render_outbox_summary,
    render_record_block,
    render_reflection_entry_detail,
    render_reflection_entry_summary,
    render_session_header,
)


def test_render_record_block_splits_header_and_body() -> None:
    assert render_record_block("[test] event", ["status=ok", "thread=default"], body="first\nsecond") == (
        "[test] event status=ok thread=default\n"
        "  first\n"
        "  second"
    )


def test_render_session_header_uses_daemon_record_style() -> None:
    assert render_session_header(daemon_status="running", thread_id="default") == (
        "[daemon] session status=running thread=default"
    )


def test_render_service_tool_log_uses_caller_and_service_tags() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="chat",
        event="service_tool_called",
        message="chat called memory service tool memory_archive",
        status="completed",
        metadata={"service_component": "memory", "tool": "memory_archive"},
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[chat] [memory] service_tool_called status=completed tool=memory_archive",
        "  chat called memory service tool memory_archive",
    ]


def test_render_discussion_trace_formats_block() -> None:
    lines = render_discussion_trace(["host: start", "turn-1:analyst: considered the idea"], title="discussion trace")

    assert lines == [
        "[discussion trace]",
        "  [host] start",
        "",
        "  [turn-1]",
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
        "[host decision] host_discussion_decision thread=default should_escalate=true",
        "  approved",
        "  user asked for multi-perspective discussion",
    ]


def test_render_persona_host_decision_does_not_repeat_escalation_reason() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="persona",
        event="host_discussion_decision",
        message="multi-perspective request",
        thread_id="default",
        status="approved",
        metadata={"should_escalate": True, "escalation_reason": "multi-perspective request"},
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[selves] host_discussion_decision thread=default should_escalate=true",
        "  approved",
        "  multi-perspective request",
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
        "[selves] persona_summary thread=default has_synthesis=true persona_count=2",
        "  deep tradeoff",
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

    assert lines[2] == "  \033[36manalyst_self\033[0m: Analyst decomposes the question."
    assert lines[3] == "  \033[31mskeptic_self\033[0m: Skeptic challenges the assumption."
    assert lines[4] == "  \033[32mbuilder_self\033[0m: Builder proposes the next move."


def test_render_discussion_log_expands_trace_metadata() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="persona",
        event="persona_discussion",
        message="New idea - approved after discussion",
        thread_id="default",
        status="approved",
        metadata={
            "candidate_id": "candidate-1",
            "discussion_trace": [
                "candidate: New idea",
                "turn-1:analyst_self: this is worth pursuing",
                "turn-1:skeptic_self: check timing first",
                "turn-1:synthesis: proceed carefully",
            ],
        },
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[selves] persona_discussion thread=default candidate_id=candidate-1",
        "  approved",
        "  New idea - approved after discussion",
        "  [discussion]",
        "    [candidate] New idea",
        "",
        "    [turn-1]",
        "      [analyst_self]     this is worth pursuing",
        "      [skeptic_self]     check timing first",
        "      [synthesis]        proceed carefully",
    ]


def test_render_outbox_records_use_shared_key_value_style() -> None:
    created = format_display_timestamp("2026-05-12T10:00:00Z")
    entry = OutboxEntry(
        id="e1",
        title="Test Title",
        body="Test Body",
        status="pending",
        idempotency_key="k1",
        deep_link="nuself://thread/default",
        created_at="2026-05-12T10:00:00Z",
    )

    assert render_outbox_summary(entry, color=False) == (
        f"e1 [pending] Test Title created={created} attempts=0 link=true"
    )
    assert render_outbox_detail(entry, color=False).splitlines() == [
        f"e1 [pending] Test Title idempotency_key=k1 attempts=0 created_at={created} deep_link=nuself://thread/default",
        "  Test Body",
    ]


def test_render_reflection_records_use_shared_key_value_style() -> None:
    created = format_display_timestamp("2026-05-12T10:00:00Z")
    entry = ReflectionEntry(
        id="reflection-candidate-1",
        title="Test idea",
        body="Body line",
        candidate_type="question",
        confidence=0.7,
        novelty=0.6,
        urgency=0.5,
        interruption_cost=0.2,
        composite_score=0.65,
        status="pending",
        discussion_approved=True,
        discussion_trace=("candidate: Test idea", "turn-1:builder_self: build it"),
        deep_link="nuself://thread/reflections",
        created_at="2026-05-12T10:00:00Z",
        reviewed_at=None,
    )

    assert render_reflection_entry_summary(entry, index=2, color=False).splitlines() == [
        f"[2] [reflection] status=[pending] created={created} type=question score=0.65",
        "  Test idea",
    ]
    assert render_reflection_entry_summary(entry, index=2, color=True).splitlines()[0].startswith(
        "[2] \033[33m[reflection]\033[0m status=\033[33m[pending]\033[0m"
    )
    assert render_reflection_entry_detail(entry, color=False).splitlines() == [
        f"[pending] Test idea id=reflection-candidate-1 type=question score=0.65 confidence=0.70 novelty=0.60 urgency=0.50 interruption=0.20 discussion=approved deep_link=nuself://thread/reflections created_at={created}",
        "  Body line",
        "  [discussion]",
        "    [candidate] Test idea",
        "",
        "    [turn-1]",
        "      [builder_self]     build it",
    ]
