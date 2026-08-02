from __future__ import annotations

import re

from _pytest.monkeypatch import MonkeyPatch

from nuself.runtime.log_event import LogEvent
from nuself.memory.model import MemoryEntry
from nuself.profile.model import ProfileItem
from nuself.memory.source_model import SourceDocument
from nuself.notification.model import OutboxEntry
from nuself.reflection.repository import ReflectionEntry
from nuself.reason.domain import ReasoningStep
from nuself.tui.memory import render_memory_entry_detail, render_memory_entry_row, render_profile_row, render_source_row
from nuself.tui.reason import render_step_watch_entry
from nuself.tui.render import (
    format_display_timestamp,
    render_discussion_trace,
    render_log_event,
    render_outbox_detail,
    render_outbox_summary,
    render_record_block,
    render_reflection_entry_detail,
    render_reflection_entry_summary,
    render_session_header,
)


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def test_render_record_block_splits_header_and_body() -> None:
    assert render_record_block("[test] event", ["status=ok", "conversation=default"], body="first\nsecond") == (
        "[test] event status=ok conversation=default\n"
        "  first\n"
        "  second"
    )


def test_render_session_header_uses_daemon_record_style() -> None:
    assert render_session_header(daemon_status="running", conversation_id="default") == (
        "[daemon] session status=running conversation=default"
    )


def test_render_service_tool_log_uses_caller_and_service_tags() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="chat",
        event="service_tool_called",
        message="chat called memory service tool memory_archive",
        conversation_id="default",
        turn_id="turn-1",
        status="completed",
        metadata={"service_component": "memory", "tool": "memory_archive", "args": {"entry_id": "m1"}, "result": 'Archived "Old memory".'},
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[chat] [memory] service_tool_called tool=memory_archive status=completed conversation=default turn=turn-1",
        "  args: {",
        '    "entry_id": "m1"',
        "  }",
        "  result:",
        '    Archived "Old memory".',
    ]


def test_render_step_watch_entry_shows_terminal_status() -> None:
    step = ReasoningStep(
        thread_id="reason-1",
        summary="Terminal step",
        delta="Finished",
        output="Done.",
        terminal_status="suggest_resolved",
        terminal_reason="All explicit goals are complete.",
    )

    assert "terminal: suggest_resolved — All explicit goals are complete." in render_step_watch_entry(step, color=False)


def test_render_workspace_service_tag_uses_256_color(monkeypatch: MonkeyPatch) -> None:
    import nuself.tui.render as render_module

    monkeypatch.setattr(render_module, "_color_depth_256", True)
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="reasoning",
        event="service_tool_called",
        message="workspace_put completed",
        status="completed",
        metadata={
            "service_component": "workspace",
            "tool": "workspace_put",
            "args": {"key": "current_round", "value": '{"round":1}'},
            "result": "Stored current_round",
        },
    )

    first_line = render_log_event(event, color=True).splitlines()[0]

    assert "\033[38;5;208m[workspace]\033[0m" in first_line
    assert "tool=\033[36mworkspace_put\033[0m" in first_line
    assert "\033[36mtool=" not in first_line
    assert "status=\033[32mcompleted\033[0m" in first_line
    assert "\033[32mstatus=" not in first_line
    assert _strip_ansi(first_line).startswith("[reasoning] [workspace] service_tool_called tool=workspace_put status=completed")


def test_render_service_tool_log_expands_nested_json_string() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="reasoning",
        event="service_tool_called",
        message="workspace_put completed",
        status="completed",
        metadata={
            "service_component": "workspace",
            "tool": "workspace_put",
            "args": {"key": "current_round", "value": '{"round":1}'},
            "result": '{"ok": true}',
        },
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[reasoning] [workspace] service_tool_called tool=workspace_put status=completed",
        "  args: {",
        '    "key": "current_round",',
        '    "value": {',
        '      "round": 1',
        "    }",
        "  }",
        "  result: {",
        '    "ok": true',
        "  }",
    ]


def test_render_service_tool_log_keeps_colored_json_brace_on_label_line() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="reasoning",
        event="service_tool_called",
        message="workspace_get completed",
        status="completed",
        metadata={
            "service_component": "workspace",
            "tool": "workspace_get",
            "args": {"key": "current_round"},
            "result": {"round": 1},
        },
    )

    rendered = render_log_event(event, color=True)

    assert "\033[90margs:\033[0m {" in rendered
    assert "\033[90margs:\033[0m\n" not in rendered
    assert "\033[90mresult:\033[0m {" in rendered
    assert "\033[90mresult:\033[0m\n" not in rendered


def test_render_service_tool_log_reads_legacy_message_body() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="reasoning",
        event="service_tool_called",
        message='args: {\n  "key": "debate_state",\n  "value": "{\\"round\\":1}"\n}\nresult: Stored debate_state',
        status="completed",
        metadata={"service_component": "workspace", "tool": "workspace_put"},
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[reasoning] [workspace] service_tool_called tool=workspace_put status=completed",
        "  args: {",
        '    "key": "debate_state",',
        '    "value": {',
        '      "round": 1',
        "    }",
        "  }",
        "  result:",
        "    Stored debate_state",
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


def test_render_persona_host_decision_does_not_repeat_escalation_reason() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="persona",
        event="host_discussion_decision",
        message="multi-perspective request",
        conversation_id="default",
        status="approved",
        metadata={"should_escalate": True, "escalation_reason": "multi-perspective request"},
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[selves] host_discussion_decision conversation=default should_escalate=true",
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
        conversation_id="default",
        status="deep tradeoff",
        metadata={"persona_count": 2, "has_synthesis": True},
    )

    assert render_log_event(event, color=False).splitlines() == [
        "[selves] persona_summary conversation=default has_synthesis=true persona_count=2",
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
        conversation_id="default",
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
        conversation_id="default",
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
        "[selves] persona_discussion conversation=default candidate_id=candidate-1",
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
        deep_link="nuself://conversation/default",
        created_at="2026-05-12T10:00:00Z",
    )

    assert render_outbox_summary(entry, color=False) == (
        f"e1 [pending] Test Title created={created} attempts=0 link=true"
    )
    assert render_outbox_detail(entry, color=False).splitlines() == [
        f"e1 [pending] Test Title idempotency_key=k1 attempts=0 created_at={created} deep_link=nuself://conversation/default",
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
        deep_link="nuself://conversation/reflections",
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
        f"[pending] Test idea id=reflection-candidate-1 type=question score=0.65 confidence=0.70 novelty=0.60 urgency=0.50 interruption=0.20 discussion=approved deep_link=nuself://conversation/reflections created_at={created}",
        "  Body line",
        "  [discussion]",
        "    [candidate] Test idea",
        "",
        "    [turn-1]",
        "      [builder_self]     build it",
    ]


def test_render_memory_records_use_subsystem_index_then_body_style() -> None:
    entry = MemoryEntry(
        id="mem_1",
        type="belief",
        title="Focus",
        body="Deep work matters.",
        tags=["work"],
        confidence=0.82,
        review_state="reviewed",
    )
    profile = ProfileItem(
        id="profile_1",
        type="preference",
        title="Prefers concise output",
        body="Keep CLI output scan-friendly.",
        tags=["cli"],
        confidence=0.9,
    )
    source = SourceDocument(
        id="src_1",
        path="notes.md",
        title="Notes",
        kind="text",
        tags=["journal"],
    )

    assert render_memory_entry_row(entry, index=0, color=False).splitlines() == [
        "[memory] [0] state=reviewed type=belief id=mem_1 tags=[work] confidence=0.82",
        "  Focus",
        "  Deep work matters.",
    ]
    assert render_memory_entry_detail(entry, color=False).splitlines() == [
        "[memory] state=reviewed type=belief id=mem_1 tags=[work] confidence=0.82 privacy=private",
        "  Focus",
        "  Deep work matters.",
    ]
    assert render_profile_row(profile, index=1, color=False).splitlines() == [
        "[profile] [1] type=preference id=profile_1 tags=[cli] confidence=0.90 importance=0.5",
        "  Prefers concise output",
        "  Keep CLI output scan-friendly.",
    ]
    assert render_source_row(source, index=2, chunk_count=3, color=False).splitlines() == [
        "[source] [2] id=src_1 chunks=3 tags=[journal] privacy=private path=notes.md",
        "  Notes",
    ]
    colored = render_memory_entry_row(entry, index=0, color=True).splitlines()[0]
    assert colored.startswith("\033[32m[memory]\033[0m [0] state=\033[32mreviewed\033[0m")
    assert "type=\033[36mbelief\033[0m" in colored
    assert "id=\033[90mmem_1\033[0m" in colored
    assert "tags=\033[90m[work]\033[0m" in colored
