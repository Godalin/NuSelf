"""Tests for reason output composition infrastructure."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import json

import pytest

from nuself.config import runtime_paths
from nuself.reason.model import ReasoningStep, ReasoningThread
from nuself.reason.output_contracts import (
    ReasonOutputManifest,
    ReasonOutputPaths,
)
from reason_output_fixtures import ReasonOutputService
from nuself.reason.errors import ReasonNotFound
from nuself.reason.repository import ReasonRepository
from reason_fixtures import ReasonService
from tests.backend import owned_backend


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path)), project_root=tmp_path, prompt_generator=_prompt)


def _prompt(*args: object, **kwargs: object) -> str:
    return "Test reasoning prompt."


def test_reason_output_plan_and_compose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def drop_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(
        "nuself.reason.output.REASON_AUDIT.write",
        drop_audit,
    )
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
    planned = output_service.plan_job(
        thread.id,
        mode="narrative",
        output_format="markdown",
        segment_size=1,
        job_sink=lambda _message: None,
    )
    def compose_steps(
        _thread: ReasoningThread,
        _manifest: ReasonOutputManifest,
        steps: Sequence[ReasoningStep],
        **_kwargs: object,
    ) -> str:
        return "\n".join(step.output for step in steps if step.output)

    manifest = output_service.compose_with_runner(
        thread.id,
        planned.job_id,
        compose_steps,
    )

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
    narrow = output_service.plan_job(
        thread.id,
        segment_size=1,
        job_sink=lambda _message: None,
    )
    wide = output_service.plan_job(
        thread.id,
        segment_size=4,
        job_sink=lambda _message: None,
    )

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
    manifest = output_service.plan_job(
        thread.id,
        job_sink=lambda _message: None,
    )
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
    manifest = output_service.plan_job(
        thread.id,
        job_sink=lambda _message: None,
    )
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
    ).plan_job(thread.id, job_sink=lambda _message: None)
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
    ).plan_job(thread.id, job_sink=lambda _message: None)
    wire = manifest.to_wire()
    del wire["updated_at"]
    wire["unexpected"] = True

    with pytest.raises(
        ValueError,
        match="missing=.*updated_at.*unknown=.*unexpected",
    ):
        ReasonOutputManifest.from_wire(wire)


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.model import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
