"""Tests for subagent-driven reason output composition via runner callable."""

from __future__ import annotations

from pathlib import Path

from nuself.reason.output import ReasonOutputService
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(tmp_path), project_root=tmp_path, prompt_generator=lambda *a, **k: "P")


def test_compose_with_runner(tmp_path: Path) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Subagent export")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, segment_size=1)

    def fake_runner(thread, manifest, steps, *, index, total):
        # create a composition that references step ids and outputs
        lines = [f"Chunk {index+1}/{total} for {thread.topic}"]
        for s in steps:
            lines.append(f"- {s.id}: {s.output}")
        return "\n".join(lines) + "\n"

    updated = output_service.compose_with_runner(thread.id, manifest.job_id, fake_runner)
    paths = output_service.job_paths(thread.id, manifest.job_id)
    assert paths.combined.is_file()
    combined = paths.combined.read_text(encoding="utf-8")
    assert "Chunk 1/2" in combined
    assert "Out A" in combined
    assert "Out B" in combined


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
