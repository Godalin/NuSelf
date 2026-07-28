"""Tests for reason output composition infrastructure."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from nuself.logs import read_log_events
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputPaths,
    ReasonOutputService,
)
from nuself.reason.errors import ReasonNotFound
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.storage import write_json_atomic


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
    assert "Chapter 1: First" in combined
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
    # Each plan_job call creates a unique job (non-deterministic job_id).
    second = output_service.plan_job(thread.id, start_index=0, end_index=0)

    jobs = output_service.list_jobs(thread.id)
    assert [job.job_id for job in jobs] == [manifest.job_id, second.job_id]
    assert manifest.job_id != second.job_id

    resumed = output_service.resume_job(thread.id, manifest.job_id)
    assert resumed.status == "complete"
    assert (output_service.job_paths(thread.id, manifest.job_id).combined).is_file()


def test_reason_output_list_isolates_corrupt_manifest_neighbors(
    tmp_path: Path,
) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("List healthy export jobs")
    service.advance_thread(
        thread.id,
        step=_step(thread.id, "Only", "Only output", "Only delta"),
    )
    output_service = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    )
    healthy = output_service.plan_job(thread.id)
    export_root = output_service.job_paths(
        thread.id,
        healthy.job_id,
    ).root.parent

    malformed_dir = export_root / "malformed-job"
    malformed_dir.mkdir()
    (malformed_dir / "manifest.json").write_text(
        '{"private":"secret body"',
        encoding="utf-8",
    )
    mismatched_dir = export_root / "mismatched-job"
    mismatched_dir.mkdir()
    write_json_atomic(
        mismatched_dir / "manifest.json",
        healthy.to_wire(),
    )
    missing_dir = export_root / "missing-job"
    missing_dir.mkdir()

    assert output_service.list_jobs(thread.id) == [healthy]

    events = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="reasoning",
        )
        if event.event == "record_decode_failed"
        and event.metadata is not None
        and event.metadata.get("collection")
        == "reason_output_manifests"
    ]
    assert {
        event.metadata["record_id"]
        for event in events
        if event.metadata is not None
    } == {"malformed-job", "mismatched-job", "missing-job"}
    assert "secret body" not in "\n".join(
        str(event.to_record()) for event in events
    )


def test_reason_output_get_job_is_strict_for_corrupt_manifest(
    tmp_path: Path,
) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Strict export lookup")
    service.advance_thread(
        thread.id,
        step=_step(thread.id, "Only", "Only output", "Only delta"),
    )
    output_service = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    )
    manifest = output_service.plan_job(thread.id)
    manifest_path = output_service.job_paths(
        thread.id,
        manifest.job_id,
    ).manifest
    manifest_path.write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        output_service.get_job(thread.id, manifest.job_id)
    with pytest.raises(ReasonNotFound):
        output_service.get_job(thread.id, "missing-job")


def test_reason_output_manifest_io_failures_propagate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Visible export storage failure")
    service.advance_thread(
        thread.id,
        step=_step(thread.id, "Only", "Only output", "Only delta"),
    )
    output_service = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    )
    manifest = output_service.plan_job(thread.id)
    manifest_path = output_service.job_paths(
        thread.id,
        manifest.job_id,
    ).manifest
    original_read_text = Path.read_text

    def fail_manifest_read(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == manifest_path:
            raise PermissionError("manifest permission denied")
        return original_read_text(
            path,
            encoding=encoding,
            errors=errors,
        )

    monkeypatch.setattr(Path, "read_text", fail_manifest_read)

    with pytest.raises(PermissionError, match="manifest permission denied"):
        output_service.list_jobs(thread.id)
    with pytest.raises(PermissionError, match="manifest permission denied"):
        output_service.get_job(thread.id, manifest.job_id)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("schema", "NuSelfReasonOutput/v2"),
        ("status", "unknown"),
        ("created_at", "2026-01-01T00:00:00"),
        ("attempts", True),
        ("sections", ["not-an-object"]),
    ),
)
def test_reason_output_manifest_rejects_invalid_wire_fields(
    tmp_path: Path,
    field_name: str,
    value: object,
) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Strict manifest schema")
    service.advance_thread(
        thread.id,
        step=_step(thread.id, "Only", "Only output", "Only delta"),
    )
    manifest = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    ).plan_job(thread.id)
    wire = manifest.to_wire()
    wire[field_name] = value

    with pytest.raises(ValueError):
        ReasonOutputManifest.from_wire(wire)


def test_reason_output_manifest_rejects_shape_drift(
    tmp_path: Path,
) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Strict manifest shape")
    service.advance_thread(
        thread.id,
        step=_step(thread.id, "Only", "Only output", "Only delta"),
    )
    manifest = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    ).plan_job(thread.id)
    wire = manifest.to_wire()
    del wire["updated_at"]
    wire["unexpected"] = True

    with pytest.raises(
        ValueError,
        match="missing=.*updated_at.*unknown=.*unexpected",
    ):
        ReasonOutputManifest.from_wire(wire)


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
