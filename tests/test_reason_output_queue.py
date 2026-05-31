"""Tests for in-memory-queue based export job processing."""

from __future__ import annotations

from pathlib import Path
import queue

import pytest

from nuself.reason.domain import ReasoningStep
from nuself.reason.domain import ReasoningThread
from nuself.reason.output import ReasonOutputManifest
from nuself.reason.output import ReasonOutputPaths
from nuself.reason.output import ReasonOutputSection
from nuself.reason.output import ReasonOutputService
from nuself.reason.output import set_enqueue_callback
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(tmp_path), project_root=tmp_path, prompt_generator=lambda *a, **k: "P")


def test_plan_enqueues_via_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """plan_job pushes to the in-memory queue when a callback is registered."""
    service = _reason_service(tmp_path)
    thread = service.start_thread("Queue export")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    q: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
    set_enqueue_callback(lambda tid, jid: q.put((tid, jid)))

    try:
        output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
        manifest = output_service.plan_job(thread.id, segment_size=1)
        paths = output_service.job_paths(thread.id, manifest.job_id)

        # No queue file exists
        assert not (paths.root / "queue").exists()

        # The event went to the in-memory queue instead
        assert q.qsize() == 1
        tid, jid = q.get()
        assert tid == thread.id
        assert jid == manifest.job_id
    finally:
        set_enqueue_callback(None)


def test_plan_without_callback_skips_enqueue(tmp_path: Path) -> None:
    """plan_job does not fail when no callback is registered (CLI / test mode)."""
    set_enqueue_callback(None)  # ensure clean
    service = _reason_service(tmp_path)
    thread = service.start_thread("No callback")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, segment_size=1)
    paths = output_service.job_paths(thread.id, manifest.job_id)

    # No queue file, no callback — but manifest was still written
    assert not (paths.root / "queue").exists()
    assert paths.manifest.is_file()


def test_compose_from_enqueued_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    updated = output_service.compose_with_runner(thread.id, manifest.job_id, fake_runner)

    # Combined output must exist and include both steps
    assert paths.combined.is_file()
    combined = paths.combined.read_text(encoding="utf-8")
    assert "Out A" in combined
    assert "Out B" in combined
    assert updated.status == "complete"


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
