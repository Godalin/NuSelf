"""Tests for file-queue based export job processing."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from nuself.reason.domain import ReasoningStep
from nuself.reason.domain import ReasoningThread
from nuself.reason.output import ReasonOutputManifest
from nuself.reason.output import ReasonOutputPaths
from nuself.reason.output import ReasonOutputSection
from nuself.reason.output import ReasonOutputService
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(tmp_path), project_root=tmp_path, prompt_generator=lambda *a, **k: "P")


def test_plan_enqueues_and_worker_processes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Queue export")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, segment_size=1)
    paths = output_service.job_paths(thread.id, manifest.job_id)

    def _fake_generate_pdf(self: ReasonOutputService, paths: ReasonOutputPaths) -> Path:
        paths.pdf.write_text("pdf", encoding="utf-8")
        return paths.pdf

    monkeypatch.setattr(ReasonOutputService, "_generate_pdf", _fake_generate_pdf)

    # Queue file should exist
    queue_file = paths.root / "queue" / f"{manifest.job_id}.json"
    assert queue_file.is_file()

    # Simulate daemon worker: atomically move to processing/ then process
    processing_dir = paths.root / "processing"
    processing_dir.mkdir(parents=True, exist_ok=True)
    processing_path = processing_dir / queue_file.name
    queue_file.replace(processing_path)

    raw = json.loads(processing_path.read_text(encoding="utf-8"))
    assert raw.get("job_id") == manifest.job_id

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

    # Process the job
    updated = output_service.compose_with_runner(thread.id, manifest.job_id, fake_runner)
    # On success the processing file would be removed by the worker; simulate that
    processing_path.unlink(missing_ok=True)

    # Combined output must exist and include both steps
    assert paths.combined.is_file()
    combined = paths.combined.read_text(encoding="utf-8")
    assert "Out A" in combined
    assert "Out B" in combined
    assert updated.status == "complete"


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
