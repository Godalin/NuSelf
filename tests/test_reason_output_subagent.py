"""Tests for subagent-driven reason output composition via runner callable."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.reason.domain import ReasoningStep
from nuself.reason.domain import ReasoningThread
from nuself.reason.output import ReasonOutputPaths
from nuself.reason.output import ReasonOutputSection
from nuself.reason.output import ReasonOutputManifest
from nuself.reason.output import ReasonOutputService
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(tmp_path), project_root=tmp_path, prompt_generator=lambda *a, **k: "P")


def test_compose_with_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Subagent export")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, segment_size=1)

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
        # create a composition that references step ids and outputs
        lines = [f"Chunk {index + 1}/{total} for {getattr(thread, 'topic', 'thread')} "]
        lines.append(f"Section: {section.title}")
        lines.append("Plan:")
        for planned in section_plan:
            lines.append(f"- {planned.index + 1}. {planned.title}")
        for s in steps:
            lines.append(f"- {s.id}: {s.output}")
        return "\n".join(lines) + "\n"

    updated = output_service.compose_with_runner(thread.id, manifest.job_id, fake_runner)
    paths = output_service.job_paths(thread.id, manifest.job_id)
    assert paths.combined.is_file()
    assert paths.pdf.is_file()
    assert updated.status == "complete"
    combined = paths.combined.read_text(encoding="utf-8")
    assert "Chunk 1/2" in combined
    assert "Composition plan" in combined
    assert "Out A" in combined
    assert "Out B" in combined


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
