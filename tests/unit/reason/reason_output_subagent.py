"""Tests for subagent-driven reason output composition via runner callable."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.config import runtime_paths
from nuself.reason.domain import ReasoningStep
from nuself.reason.domain import ReasoningThread
from nuself.reason.output import ReasonOutputPaths
from nuself.reason.output import ReasonOutputSection
from nuself.reason.output import ReasonOutputManifest
from nuself.reason.output import ReasonOutputService
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.storage import get_default_backend


def _reason_service(tmp_path: Path) -> ReasonService:
    return ReasonService(repository=ReasonRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path)), project_root=tmp_path, prompt_generator=lambda *a, **k: "P")


def test_compose_with_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Subagent export")
    service.advance_thread(thread.id, step=_step(thread.id, "A", "Out A", "D A"))
    service.advance_thread(thread.id, step=_step(thread.id, "B", "Out B", "D B"))

    output_service = ReasonOutputService(project_root=tmp_path, reason_service=service)
    manifest = output_service.plan_job(thread.id, segment_size=1)

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
    assert "Out A" in combined
    assert "Out B" in combined


def test_chunk_failure_log_cannot_mask_runner_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _reason_service(tmp_path)
    thread = service.start_thread("Subagent export")
    service.advance_thread(
        thread.id,
        step=_step(thread.id, "A", "Out A", "D A"),
    )
    output_service = ReasonOutputService(
        project_root=tmp_path,
        reason_service=service,
    )
    manifest = output_service.plan_job(thread.id, segment_size=1)
    primary_error = RuntimeError("runner failed")

    def fail_runner(
        thread: ReasoningThread,
        manifest: ReasonOutputManifest,
        steps: list[ReasoningStep],
        *,
        section: ReasonOutputSection,
        section_plan: tuple[ReasonOutputSection, ...],
        index: int,
        total: int,
    ) -> str:
        raise primary_error

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    def drop_lifecycle_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.reason.output.write_reason_audit",
        drop_lifecycle_audit,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ), pytest.raises(RuntimeError) as captured:
        output_service.compose_with_runner(
            thread.id,
            manifest.job_id,
            fail_runner,
        )

    assert captured.value is primary_error
    paths = output_service.job_paths(thread.id, manifest.job_id)
    assert list(paths.chunks_dir.glob("chunk-*.md")) == []


def _step(thread_id: str, summary: str, output: str, delta: str):
    from nuself.reason.domain import ReasoningStep

    return ReasoningStep(thread_id=thread_id, summary=summary, output=output, delta=delta)
