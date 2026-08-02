"""Tests for in-memory-queue based export job processing."""

from __future__ import annotations

import queue
from collections.abc import Sequence
from pathlib import Path

import pytest

from nuself.config.settings import runtime_paths
from nuself.log.reader import read_log_events
from tests.backend import owned_backend
from nuself.reason.model import ReasoningStep, ReasoningThread
from nuself.reason.output_contracts import (
    ReasonOutputManifest,
    ReasonOutputPaths,
    ReasonOutputSection,
)
from reason_output_fixtures import ReasonOutputService
from nuself.reason.repository import ReasonRepository
from reason_fixtures import ReasonService
from nuself.runtime.job.message import JobMessage


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(
        repository=ReasonRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path)),
        project_root=tmp_path,
        prompt_generator=lambda *a, **k: "P",
    )


def test_plan_publishes_typed_job_message(tmp_path: Path) -> None:
    """plan_job publishes through its injected job sink."""
    service = _reason_service(tmp_path)
    thread = service.start_thread("Queue export")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    q: queue.SimpleQueue[JobMessage] = queue.SimpleQueue()
    output_service = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    )
    manifest = output_service.plan_job(
        thread.id,
        segment_size=1,
        job_sink=q.put,
    )
    paths = output_service.job_paths(thread.id, manifest.job_id)

    assert not (paths.root / "queue").exists()
    assert q.qsize() == 1
    message = q.get()
    assert message.envelope.name == "reason.output.export"
    assert message.resource_id == thread.id
    assert message.job_id == manifest.job_id


def test_plan_preserves_durable_job_when_wakeup_fails(
    tmp_path: Path,
) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Recoverable wake-up")
    service.advance_thread(
        thread.id,
        step=_step(thread.id, "A", "Out A", "D A"),
    )

    def fail_wakeup(message: JobMessage) -> None:
        try:
            raise OSError("queue unavailable")
        except OSError as exc:
            raise RuntimeError("wake-up rejected") from exc

    output_service = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    )

    manifest = output_service.plan_job(
        thread.id,
        segment_size=1,
        job_sink=fail_wakeup,
    )
    paths = output_service.job_paths(thread.id, manifest.job_id)

    assert paths.manifest.is_file()
    assert manifest.status == "planned"
    events = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if event.event == "export_job_enqueue_failed"
    ]
    assert len(events) == 1
    assert events[0].error == "wake-up rejected <- queue unavailable"
    assert events[0].metadata == {
        "thread_id": thread.id,
        "job_id": manifest.job_id,
    }


def test_section_planners_are_isolated_per_service(tmp_path: Path) -> None:
    def planner(title: str):
        def plan(
            thread: ReasoningThread,
            steps: Sequence[ReasoningStep],
            mode: str,
        ) -> tuple[ReasonOutputSection, ...]:
            return (
                ReasonOutputSection(
                    index=0,
                    title=title,
                    focus=mode,
                    step_ids=tuple(step.id for step in steps),
                    source_start_index=0,
                    source_end_index=len(steps) - 1,
                    summary=thread.topic,
                ),
            )

        return plan

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    reason_a = _reason_service(root_a)
    reason_b = _reason_service(root_b)
    thread_a = reason_a.start_thread("A")
    thread_b = reason_b.start_thread("B")
    reason_a.advance_thread(
        thread_a.id,
        step=_step(thread_a.id, "A", "Out A", "D A"),
    )
    reason_b.advance_thread(
        thread_b.id,
        step=_step(thread_b.id, "B", "Out B", "D B"),
    )
    output_a = ReasonOutputService(
        root_a,
        reason_service=reason_a,
        section_planner=planner("Planner A"),
    )
    output_b = ReasonOutputService(
        root_b,
        reason_service=reason_b,
        section_planner=planner("Planner B"),
    )

    manifest_a = output_a.plan_job(
        thread_a.id,
        job_sink=lambda _message: None,
    )
    manifest_b = output_b.plan_job(
        thread_b.id,
        job_sink=lambda _message: None,
    )

    assert manifest_a.sections[0].title == "Planner A"
    assert manifest_b.sections[0].title == "Planner B"


def test_compose_from_enqueued_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate the daemon worker: receive a queue event, then compose."""
    service = _reason_service(tmp_path)
    thread = service.start_thread("Compose from queue")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(
        thread.id,
        segment_size=1,
        job_sink=lambda _message: None,
    )
    paths = output_service.job_paths(thread.id, manifest.job_id)

    def _fake_generate_pdf(
        self: ReasonOutputService,
        paths: ReasonOutputPaths,
        *,
        thread_id: str,
        job_id: str,
    ) -> Path:
        del thread_id, job_id
        paths.pdf.write_text("pdf", encoding="utf-8")
        return paths.pdf

    monkeypatch.setattr(ReasonOutputService, "_generate_pdf", _fake_generate_pdf)

    def fake_runner(
        thread: ReasoningThread,
        manifest: ReasonOutputManifest,
        steps: list[ReasoningStep],
        *,
        section: ReasonOutputSection,
        section_plan: tuple[ReasonOutputSection, ...],
        index: int,
        total: int,
    ) -> str:
        lines = [f"Chunk {index + 1}/{total} for {getattr(thread, 'topic', 'thread')}"]
        lines.append(f"Section: {section.title}")
        for s in steps:
            lines.append(f"- {s.id}: {s.output}")
        return "\n".join(lines) + "\n"

    # The daemon worker would dequeue and call compose_with_runner
    updated = output_service.compose_with_runner(
        thread.id, manifest.job_id, fake_runner
    )

    # Combined output must exist and include both steps
    assert paths.combined.is_file()
    combined = paths.combined.read_text(encoding="utf-8")
    assert "Out A" in combined
    assert "Out B" in combined
    assert updated.status == "complete"


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.model import ReasoningStep

    return ReasoningStep(
        thread_id=thread_id, summary=summary, output=output, delta=delta
    )
