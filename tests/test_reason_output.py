"""Tests for reason output composition infrastructure."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from nuself.reason.output import ReasonOutputService
from nuself.reason.output import ReasonOutputPaths
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(tmp_path), project_root=tmp_path, prompt_generator=_prompt)


def _prompt(*args: object, **kwargs: object) -> str:
    return "Test reasoning prompt."


def test_reason_output_plan_and_compose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Export me")
    first = service.advance_thread(
        thread.id,
        step=_step(thread.id, "First", "First output", "First delta"),
    )
    service.advance_thread(
        first.id,
        step=_step(thread.id, "Second", "Second output", "Second delta"),
    )

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)

    def _fake_generate_pdf(self: ReasonOutputService, paths: ReasonOutputPaths) -> Path:
        paths.pdf.write_text("pdf", encoding="utf-8")
        return paths.pdf

    monkeypatch.setattr(ReasonOutputService, "_generate_pdf", _fake_generate_pdf)
    manifest = output_service.start_job(thread.id, mode="narrative", output_format="markdown", segment_size=1)

    paths = output_service.job_paths(thread.id, manifest.job_id)
    assert paths.manifest.is_file()
    assert paths.progress.is_file()
    assert paths.combined.is_file()
    assert paths.pdf.is_file()

    data = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert data["thread_id"] == thread.id
    assert data["status"] == "complete"
    assert len(data["sections"]) == 1
    assert len(data["chunks"]) == 2
    assert data["sections"][0]["title"].startswith("Chapter 1:")

    combined = paths.combined.read_text(encoding="utf-8")
    assert "Composition plan" in combined
    assert "First output" in combined
    assert "Second output" in combined


def test_reason_output_section_plan_is_independent_of_chunk_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Stable chapters")
    for index in range(1, 11):
        service.advance_thread(
            thread.id,
            step=_step(thread.id, f"Step {index}", f"Output {index}", f"Delta {index}"),
        )

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)

    def _fake_generate_pdf(self: ReasonOutputService, paths: ReasonOutputPaths) -> Path:
        paths.pdf.write_text("pdf", encoding="utf-8")
        return paths.pdf

    monkeypatch.setattr(ReasonOutputService, "_generate_pdf", _fake_generate_pdf)
    narrow = output_service.plan_job(thread.id, segment_size=1)
    wide = output_service.plan_job(thread.id, segment_size=4)

    narrow_sections = [
        {
            "index": section.index,
            "title": section.title,
            "focus": section.focus,
            "step_ids": list(section.step_ids),
            "source_start_index": section.source_start_index,
            "source_end_index": section.source_end_index,
            "summary": section.summary,
        }
        for section in narrow.sections
    ]
    wide_sections = [
        {
            "index": section.index,
            "title": section.title,
            "focus": section.focus,
            "step_ids": list(section.step_ids),
            "source_start_index": section.source_start_index,
            "source_end_index": section.source_end_index,
            "summary": section.summary,
        }
        for section in wide.sections
    ]
    assert narrow_sections == wide_sections


def test_reason_output_list_jobs_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Resume me")
    service.advance_thread(thread.id, step=_step(thread.id, "Only", "Only output", "Only delta"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)

    def _fake_generate_pdf(self: ReasonOutputService, paths: ReasonOutputPaths) -> Path:
        paths.pdf.write_text("pdf", encoding="utf-8")
        return paths.pdf

    monkeypatch.setattr(ReasonOutputService, "_generate_pdf", _fake_generate_pdf)
    manifest = output_service.plan_job(thread.id, start_index=0, end_index=0)
    repeat_manifest = output_service.plan_job(thread.id, start_index=0, end_index=0)

    jobs = output_service.list_jobs(thread.id)
    assert [job.job_id for job in jobs] == [manifest.job_id]
    assert repeat_manifest.job_id == manifest.job_id
    assert output_service.job_paths(thread.id, manifest.job_id).root == output_service.job_paths(thread.id, repeat_manifest.job_id).root

    resumed = output_service.resume_job(thread.id, manifest.job_id)
    assert resumed.status == "complete"
    assert (output_service.job_paths(thread.id, manifest.job_id).combined).is_file()


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
