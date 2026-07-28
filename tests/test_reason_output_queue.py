"""Tests for in-memory-queue based export job processing."""

from __future__ import annotations

import queue
from pathlib import Path

import pytest

from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputPaths,
    ReasonOutputSection,
    ReasonOutputService,
)
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.runtime.jobs import JobMessage


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(
        repository=ReasonRepository(tmp_path),
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
        job_sink=q.put,
    )
    manifest = output_service.plan_job(thread.id, segment_size=1)
    paths = output_service.job_paths(thread.id, manifest.job_id)

    assert not (paths.root / "queue").exists()
    assert q.qsize() == 1
    message = q.get()
    assert message.envelope.name == "reason.output.export"
    assert message.resource_id == thread.id
    assert message.job_id == manifest.job_id


def test_plan_without_job_sink_skips_enqueue(tmp_path: Path) -> None:
    """plan_job does not fail without a job sink (CLI / test mode)."""
    service = _reason_service(tmp_path)
    thread = service.start_thread("No callback")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, segment_size=1)
    paths = output_service.job_paths(thread.id, manifest.job_id)

    # No queue file, no callback — but manifest was still written
    assert not (paths.root / "queue").exists()
    assert paths.manifest.is_file()


def test_compose_from_enqueued_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate the daemon worker: receive a queue event, then compose."""
    service = _reason_service(tmp_path)
    thread = service.start_thread("Compose from queue")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, segment_size=1)
    paths = output_service.job_paths(thread.id, manifest.job_id)

    def _fake_generate_pdf(self: ReasonOutputService, paths: ReasonOutputPaths) -> Path:
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
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(
        thread_id=thread_id, summary=summary, output=output, delta=delta
    )
