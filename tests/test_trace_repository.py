from __future__ import annotations

from pathlib import Path

import pytest

from nuself.trace import ThoughtTrace, TraceNotFound, TraceRepository, TraceRecorder


def test_trace_repository_saves_lists_searches_and_links(tmp_path: Path) -> None:
    repo = TraceRepository(tmp_path)
    recorder = TraceRecorder(repository=repo)

    trace = recorder.record_chat_turn(
        title="Answer about memory time",
        summary="NuSelf answered using temporal memory context.",
        user_input="thread:default:1:user",
        assistant_output="thread:default:2:assistant",
        thread_id="default",
        evidence_refs=["mem_123"],
        participants=["chat_agent", "memory"],
        decision_points=["Memory context included observed_at."],
    )
    link = recorder.link(trace.id, "mem_123", "cites", "The answer cited a memory entry.")

    traces = repo.list_traces()
    matches = repo.search_traces("temporal")
    links = repo.links_for(trace.id)

    assert traces == [trace]
    assert matches == [trace]
    assert links == [link]
    assert (tmp_path / "private" / "traces" / "traces" / f"{trace.id}.json").is_file()
    assert (tmp_path / "private" / "traces" / "links" / f"{link.id}.json").is_file()
    assert (tmp_path / "private" / "traces" / "index.json").is_file()


def test_trace_repository_hides_internal_records_by_default(tmp_path: Path) -> None:
    repo = TraceRepository(tmp_path)
    private = repo.save_trace(
        ThoughtTrace(kind="decision", title="Private decision", summary="Visible locally.")
    )
    internal = repo.save_trace(
        ThoughtTrace(kind="decision", title="Internal decision", summary="Hidden normally.", visibility="internal")
    )

    assert repo.list_traces() == [private]
    assert repo.list_traces(visibility="internal") == [internal]
    assert repo.list_traces(visibility="all") == [private, internal]


def test_trace_repository_resolves_display_index(tmp_path: Path) -> None:
    repo = TraceRepository(tmp_path)
    first = repo.save_trace(ThoughtTrace(kind="decision", title="First", summary="First trace."))
    second = repo.save_trace(ThoughtTrace(kind="decision", title="Second", summary="Second trace."))

    assert repo.resolve_trace("1", by_index=True) == first
    assert repo.resolve_trace("2", by_index=True) == second
    with pytest.raises(TraceNotFound):
        repo.resolve_trace("3", by_index=True)
