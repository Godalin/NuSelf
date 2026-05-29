"""Tests for reason output composition infrastructure."""

from __future__ import annotations

from pathlib import Path
import json

from nuself.reason.output import ReasonOutputService
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(tmp_path), project_root=tmp_path, prompt_generator=_prompt)


def _prompt(*args: object, **kwargs: object) -> str:
    return "Test reasoning prompt."


def test_reason_output_plan_and_compose(tmp_path: Path) -> None:
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
    manifest = output_service.start_job(thread.id, mode="narrative", output_format="markdown", segment_size=1)

    paths = output_service.job_paths(thread.id, manifest.job_id)
    assert paths.manifest.is_file()
    assert paths.progress.is_file()
    assert paths.combined.is_file()

    data = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert data["thread_id"] == thread.id
    assert data["status"] == "complete"
    assert len(data["chunks"]) == 2

    combined = paths.combined.read_text(encoding="utf-8")
    assert "First output" in combined
    assert "Second output" in combined


def test_reason_output_list_jobs_and_resume(tmp_path: Path) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Resume me")
    service.advance_thread(thread.id, step=_step(thread.id, "Only", "Only output", "Only delta"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, start_index=0, end_index=0)

    jobs = output_service.list_jobs(thread.id)
    assert [job.job_id for job in jobs] == [manifest.job_id]

    resumed = output_service.resume_job(thread.id, manifest.job_id)
    assert resumed.status == "complete"
    assert (output_service.job_paths(thread.id, manifest.job_id).combined).is_file()


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
