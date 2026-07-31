"""Reason output composition service and export job storage."""


from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Callable, Sequence, cast
from uuid import uuid4

from nuself.clock import utc_now, utc_now_iso
from nuself.reason.domain import ReasoningStep, ReasoningThread, partition_steps
from nuself.reason.errors import ReasonNotFound
from nuself.reason.output_contracts import (
    REASON_OUTPUT_FORMATS,
    REASON_OUTPUT_MODES,
    ReasonOutputChunk,
    ReasonOutputManifest,
    ReasonOutputPaths,
    ReasonOutputProgress,
    ReasonOutputSection,
    SectionPlanner,
)
from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
from nuself.reason.audit import (
    report_reason_failure,
    write_reason_audit,
)
from nuself.reason.service import ReasonService
from nuself.runtime.diagnostics import (
    diagnostic_exception_message,
    redact_sensitive_text,
)
from nuself.runtime.jobs import JobSink
from nuself.runtime.job_definitions import JobDefinitionRegistry
from nuself.runtime.observability import report_corrupt_record
from nuself.storage import write_json_atomic, write_text_atomic
from nuself.private_fs import ensure_private_directory
from nuself.workspace import PrivateWorkspaceStore

class ReasonOutputService:
    """Plan, compose, and persist reason-scoped long-form export jobs."""

    def __init__(
        self,
        project_root: Path,
        reason_service: ReasonService,
        workspace_store: PrivateWorkspaceStore,
        job_sink: JobSink | None = None,
        job_definitions: JobDefinitionRegistry | None = None,
        section_planner: SectionPlanner | None = None,
    ) -> None:
        self._reason_service = reason_service
        self._project_root = project_root
        self._workspace_store = workspace_store
        self._job_sink = job_sink
        self._job_definitions = (
            job_definitions
            if job_definitions is not None
            else build_reason_job_definition_registry()
        )
        self._section_planner = section_planner

    def list_jobs(self, thread_id: str) -> list[ReasonOutputManifest]:
        root = self._export_root(thread_id)
        if not root.exists():
            return []
        jobs_dir = root / "jobs"
        if not jobs_dir.exists():
            return []
        jobs: list[ReasonOutputManifest] = []
        for job_dir in jobs_dir.iterdir():
            if not job_dir.is_dir():
                continue
            manifest_path = job_dir / "manifest.json"
            try:
                manifest = self._read_manifest(manifest_path)
                if (
                    manifest.job_id != job_dir.name
                    or manifest.thread_id != thread_id
                ):
                    raise ValueError(
                        "reason output manifest identity does not match its path"
                    )
            except FileNotFoundError as exc:
                self._report_corrupt_manifest(exc, job_dir.name)
                continue
            except (json.JSONDecodeError, ValueError) as exc:
                self._report_corrupt_manifest(exc, job_dir.name)
                continue
            jobs.append(manifest)
        return sorted(jobs, key=lambda m: (m.created_at, m.job_id))

    def get_job(self, thread_id: str, job_id: str) -> ReasonOutputManifest:
        # The job directory is named by job_id, so read its manifest directly
        # instead of scanning and parsing every job manifest under the thread.
        try:
            manifest_path = self._job_paths(thread_id, job_id).manifest
        except ValueError as exc:
            raise ReasonNotFound(job_id) from exc
        try:
            manifest = self._read_manifest(manifest_path)
        except FileNotFoundError as exc:
            raise ReasonNotFound(job_id) from exc
        if manifest.job_id != job_id or manifest.thread_id != thread_id:
            raise ValueError(
                "reason output manifest identity does not match its path"
            )
        return manifest

    def plan_job(
        self,
        thread_id: str,
        *,
        mode: str = "narrative",
        output_format: str = "markdown",
        start_index: int = 0,
        end_index: int | None = None,
        segment_size: int = 5,
    ) -> ReasonOutputManifest:
        thread = self._reason_service.show_thread(thread_id)
        steps = self._reason_service.list_steps(thread.id)
        selected = _select_steps(steps, start_index=start_index, end_index=end_index)
        if not selected:
            raise RuntimeError("Cannot plan export job: selected reason range is empty")
        mode = _validate_choice(mode, REASON_OUTPUT_MODES, label="mode")
        output_format = _validate_choice(output_format, REASON_OUTPUT_FORMATS, label="output format")
        segment_size = _validate_positive_int(segment_size, label="segment_size")
        if self._section_planner is not None:
            sections = self._section_planner(thread, list(selected), mode)
        else:
            sections = plan_sections(thread, list(selected), mode=mode)
        job_id = _export_job_id(
            thread.id,
            mode=mode,
            output_format=output_format,
            start_index=start_index,
            end_index=end_index,
            segment_size=segment_size,
            source_step_ids=tuple(step.id for step in selected),
        )
        paths = self._job_paths(thread.id, job_id)
        _clear_job_artifacts(paths)
        ensure_private_directory(paths.root)
        manifest = ReasonOutputManifest(
            job_id=job_id,
            thread_id=thread.id,
            mode=mode,
            output_format=output_format,
            source_start_index=start_index,
            source_end_index=end_index,
            source_step_ids=tuple(step.id for step in selected),
            segment_size=segment_size,
            sections=tuple(sections),
        )
        self._write_manifest(paths.manifest, manifest)
        self._write_progress(
            paths.progress,
            ReasonOutputProgress(
                job_id=job_id,
                thread_id=thread.id,
                status=manifest.status,
                completed_chunks=(),
                total_chunks=_chunk_count(len(selected), segment_size),
                pdf_status="pending",
                pdf_path=None,
                updated_at=manifest.updated_at,
            ),
        )
        write_reason_audit(
            "reason_output_planned",
            project_root=self._project_root,
            metadata={
                "thread_id": thread.id,
                "job_id": job_id,
                "mode": mode,
                "output_format": output_format,
                "source_start_index": start_index,
                "source_end_index": end_index,
                "segment_size": segment_size,
                "step_count": len(selected),
            },
        )

        job_sink = self._job_sink
        if job_sink is not None:
            job_message = self._job_definitions.create(
                name=REASON_OUTPUT_JOB_NAME,
                producer="reasoning",
                job_id=job_id,
                resource_id=thread.id,
                payload={"mode": mode, "output_format": output_format},
            )

            def enqueue() -> bool:
                job_sink(job_message)
                return True

            try:
                enqueued = enqueue()
            except Exception as exc:
                report_reason_failure(
                    exc,
                    event="export_job_enqueue_failed",
                    project_root=self._project_root,
                    metadata={"thread_id": thread.id, "job_id": job_id},
                )
                enqueued = False
            if enqueued:
                write_reason_audit(
                    "export_job_enqueued",
                    project_root=self._project_root,
                    metadata={
                        "thread_id": thread.id,
                        "job_id": job_id,
                    },
                )
        return manifest

    def compose_job(self, thread_id: str, job_id: str) -> ReasonOutputManifest:
        return self.compose_with_runner(thread_id, job_id, _compose_runner)

    def start_job(
        self,
        thread_id: str,
        *,
        mode: str = "narrative",
        output_format: str = "markdown",
        start_index: int = 0,
        end_index: int | None = None,
        segment_size: int = 5,
        compose: bool = True,
    ) -> ReasonOutputManifest:
        manifest = self.plan_job(
            thread_id,
            mode=mode,
            output_format=output_format,
            start_index=start_index,
            end_index=end_index,
            segment_size=segment_size,
        )
        if compose:
            return self.compose_job(thread_id, manifest.job_id)
        return manifest

    def resume_job(self, thread_id: str, job_id: str) -> ReasonOutputManifest:
        return self.compose_job(thread_id, job_id)

    def compose_with_runner(self, thread_id: str, job_id: str, runner: Callable[..., str]) -> ReasonOutputManifest:
        """Compose the job using an injected runner callable for each segment.

        The runner callable is invoked for each segment with signature:
            runner(thread: ReasoningThread, manifest: ReasonOutputManifest, steps: Sequence[ReasoningStep], *, section: ReasonOutputSection, section_plan: Sequence[ReasonOutputSection], index: int, total: int) -> str

        The runner must return the final chunk text for that segment. This allows
        the caller to implement subagent-driven LLM composition while the
        service handles persistence and manifest updates.
        """
        manifest = self.get_job(thread_id, job_id)
        thread = self._reason_service.show_thread(thread_id)
        step_map = {step.id: step for step in self._reason_service.list_steps(thread.id)}
        selected = [step_map[step_id] for step_id in manifest.source_step_ids if step_id in step_map]
        if len(selected) != len(manifest.source_step_ids):
            raise RuntimeError("Cannot compose export job: one or more source steps are missing")

        paths = self._job_paths(thread.id, job_id)
        ensure_private_directory(paths.root)
        chunks: list[ReasonOutputChunk] = []
        section_plan = self._resolve_section_plan(thread, manifest, selected)
        total = _chunk_count(len(selected), manifest.segment_size)
        batch_start = 0
        for index, batch in enumerate(partition_steps(selected, manifest.segment_size)):
            section = _section_for_position(section_plan, batch_start)
            filename = _chunk_filename(index)
            chunk_path = paths.chunks_dir / filename
            batch_start += len(batch)

            # Skip already-written chunks so a mid-export failure doesn't
            # waste LLM calls on retry.
            if chunk_path.exists():
                chunk = ReasonOutputChunk(index=index, filename=filename, step_ids=tuple(step.id for step in batch))
                chunks.append(chunk)
                write_reason_audit(
                    "reason_output_chunk_skipped",
                    project_root=self._project_root,
                    metadata={"thread_id": thread.id, "job_id": manifest.job_id, "chunk_index": index},
                )
                continue

            # Emit chunk-level start event
            write_reason_audit(
                "reason_output_chunk_started",
                project_root=self._project_root,
                metadata={"thread_id": thread.id, "job_id": manifest.job_id, "chunk_index": index},
            )

            # Runner composes the chunk text (e.g., via a subagent/LLM)
            try:
                start_ts = utc_now().timestamp()
                composed_text = runner(thread, manifest, batch, section=section, section_plan=section_plan, index=index, total=total)
                duration_ms = int((utc_now().timestamp() - start_ts) * 1000)
            except Exception as exc:
                report_reason_failure(
                    exc,
                    event="reason_output_chunk_failed",
                    project_root=self._project_root,
                    metadata={"thread_id": thread.id, "job_id": manifest.job_id, "chunk_index": index},
                )
                raise

            # persist chunk
            write_text_atomic(
                chunk_path,
                _render_chunk_document(
                    thread,
                    manifest,
                    section=section,
                    section_plan=section_plan,
                    body=composed_text,
                ),
            )

            # Emit chunk completed event
            write_reason_audit(
                "reason_output_chunk_completed",
                project_root=self._project_root,
                duration_ms=duration_ms,
                metadata={
                    "thread_id": thread.id,
                    "job_id": manifest.job_id,
                    "chunk_index": index,
                },
            )
            chunk = ReasonOutputChunk(index=index, filename=filename, step_ids=tuple(step.id for step in batch))
            chunks.append(chunk)

        return self._finalize_job(thread, manifest, paths, chunks, section_plan)

    def job_paths(self, thread_id: str, job_id: str) -> ReasonOutputPaths:
        return self._job_paths(thread_id, job_id)

    def _job_paths(self, thread_id: str, job_id: str) -> ReasonOutputPaths:
        _validate_segment(thread_id, "thread id")
        _validate_segment(job_id, "job id")
        workspace = self._workspace_store.ensure(thread_id)
        root = workspace.artifacts / "jobs" / job_id
        return ReasonOutputPaths(
            root=root,
            manifest=root / "manifest.json",
            progress=root / "progress.json",
            combined=root / "combined.md",
            pdf=root / "combined.pdf",
            chunks_dir=root,
        )

    def _export_root(self, thread_id: str) -> Path:
        workspace = self._workspace_store.ensure(thread_id)
        return workspace.artifacts

    def _finalize_job(
        self,
        thread: ReasoningThread,
        manifest: ReasonOutputManifest,
        paths: ReasonOutputPaths,
        chunks: Sequence[ReasonOutputChunk],
        section_plan: Sequence[ReasonOutputSection],
    ) -> ReasonOutputManifest:
        combined_text = _combine_chunks(thread, manifest, paths, chunks, section_plan=section_plan)
        write_text_atomic(paths.combined, combined_text)
        updated = manifest.with_updates(status="complete", chunks=tuple(chunks), sections=tuple(section_plan))
        self._write_manifest(paths.manifest, updated)
        self._write_progress(
            paths.progress,
            ReasonOutputProgress(
                job_id=manifest.job_id,
                thread_id=thread.id,
                status=updated.status,
                completed_chunks=tuple(chunk.index for chunk in chunks),
                total_chunks=len(chunks),
                pdf_status="pending",
                pdf_path=None,
                updated_at=updated.updated_at,
            ),
        )
        write_reason_audit(
            "reason_output_composed",
            project_root=self._project_root,
            metadata={
                "thread_id": thread.id,
                "job_id": manifest.job_id,
                "chunk_count": len(chunks),
            },
        )

        # Generate PDF with timeout — combined.md is already written.
        write_reason_audit(
            "reason_output_pdf_started",
            project_root=self._project_root,
            metadata={
                "thread_id": thread.id,
                "job_id": manifest.job_id,
            },
        )
        pdf_path = self._generate_pdf(
            paths,
            thread_id=thread.id,
            job_id=manifest.job_id,
        )
        pdf_status, pdf_path_str = self._pdf_result(pdf_path, paths)
        self._write_progress(
            paths.progress,
            ReasonOutputProgress(
                job_id=manifest.job_id,
                thread_id=thread.id,
                status=updated.status,
                completed_chunks=tuple(chunk.index for chunk in chunks),
                total_chunks=len(chunks),
                pdf_status=pdf_status,
                pdf_path=pdf_path_str,
                updated_at=utc_now_iso(),
            ),
        )
        return updated

    def _read_manifest(self, path: Path) -> ReasonOutputManifest:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("reason output manifest must be a JSON object")
        return ReasonOutputManifest.from_wire(cast(dict[str, object], raw))

    def _report_corrupt_manifest(
        self,
        exc: Exception,
        job_id: str,
    ) -> None:
        report_corrupt_record(
            exc,
            component="reasoning",
            collection="reason_output_manifests",
            record_id=job_id,
            project_root=self._project_root,
        )

    def _write_manifest(self, path: Path, manifest: ReasonOutputManifest) -> None:
        write_json_atomic(path, manifest.to_wire())

    def _write_progress(self, path: Path, progress: ReasonOutputProgress) -> None:
        write_json_atomic(path, progress.to_wire())

    def _resolve_section_plan(
        self,
        thread: ReasoningThread,
        manifest: ReasonOutputManifest,
        selected: Sequence[ReasoningStep],
    ) -> tuple[ReasonOutputSection, ...]:
        if manifest.sections:
            return manifest.sections
        return plan_sections(thread, list(selected), mode=manifest.mode)

    def _generate_pdf(
        self,
        paths: ReasonOutputPaths,
        *,
        thread_id: str,
        job_id: str,
    ) -> Path | None:
        script = self._project_root / "scripts" / "mdpdf.sh"
        if not script.is_file() or not paths.combined.is_file():
            return None
        try:
            subprocess.run(
                ["bash", str(script), str(paths.combined)],
                cwd=self._project_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            write_reason_audit(
                "reason_output_pdf_timeout",
                project_root=self._project_root,
                metadata={"thread_id": thread_id, "job_id": job_id},
            )
            return None
        except subprocess.CalledProcessError as exc:
            process_error = next(
                (
                    value.strip()
                    for value in (exc.stderr, exc.stdout)
                    if isinstance(value, str) and value.strip()
                ),
                "",
            )
            error = (
                redact_sensitive_text(process_error)
                if process_error
                else diagnostic_exception_message(exc)
            )
            write_reason_audit(
                "reason_output_pdf_failed",
                project_root=self._project_root,
                error=error,
                metadata={"thread_id": thread_id, "job_id": job_id},
            )
            return None
        if paths.pdf.is_file():
            write_reason_audit(
                "reason_output_pdf_created",
                project_root=self._project_root,
                metadata={"thread_id": thread_id, "job_id": job_id},
            )
            return paths.pdf
        return None

    @staticmethod
    def _pdf_result(pdf_path: Path | None, paths: ReasonOutputPaths) -> tuple[str, str | None]:
        if pdf_path is not None:
            return ("generated", str(pdf_path))
        if paths.pdf.exists():
            return ("generated", str(paths.pdf))
        return ("failed", None)


def _compose_runner(
    thread: ReasoningThread,
    manifest: ReasonOutputManifest,
    steps: Sequence[ReasoningStep],
    *,
    index: int,
    total: int,
    **kw: object,
) -> str:
    """Default chunk runner used by compose_job."""
    return _render_chunk(thread, manifest, steps, index=index, total=total)


def _render_chunk(
    thread: ReasoningThread,
    manifest: ReasonOutputManifest,
    steps: Sequence[ReasoningStep],
    *,
    index: int,
    total: int,
) -> str:
    lines: list[str] = []
    for step in steps:
        lines.append(f"## {step.summary}")
        lines.append("")
        if step.output:
            lines.append(step.output)
        elif step.delta:
            lines.append(step.delta)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _combine_chunks(
    thread: ReasoningThread,
    manifest: ReasonOutputManifest,
    paths: ReasonOutputPaths,
    chunks: Sequence[ReasonOutputChunk],
    *,
    section_plan: Sequence[ReasonOutputSection],
) -> str:
    lines = [f"# {thread.topic}", ""]
    step_order = list(manifest.source_step_ids)
    prev_section_index = -1
    for chunk in chunks:
        chunk_path = paths.chunks_dir / chunk.filename
        try:
            raw = chunk_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            lines.append(f"*[Missing chunk {chunk.filename}]*")
            lines.append("")
            continue
        # Chunk files start with '# {section.title}' — strip it since
        # _combine_chunks manages section headings with dedup.
        first_newline = raw.find("\n")
        if first_newline != -1 and raw[:first_newline].startswith("#"):
            body = raw[first_newline + 1 :].strip()
        else:
            body = raw.strip()

        step_pos = next((i for i, sid in enumerate(step_order) if sid in chunk.step_ids), -1)
        section = _section_for_position(section_plan, step_pos)
        if section.index != prev_section_index:
            lines.append(f"# {section.title}")
            lines.append("")
            prev_section_index = section.index

        lines.append(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_chunk_document(
    thread: ReasoningThread,
    manifest: ReasonOutputManifest,
    *,
    section: ReasonOutputSection,
    section_plan: Sequence[ReasonOutputSection],
    body: str,
) -> str:
    lines = [f"# {section.title}", ""]
    lines.append(body.rstrip())
    return "\n".join(lines).rstrip() + "\n"


def plan_sections(
    thread: ReasoningThread,
    selected: list[ReasoningStep],
    *,
    mode: str,
) -> tuple[ReasonOutputSection, ...]:
    """Partition steps into sections based on mode and step count."""
    batches = tuple(partition_steps(selected, _section_window_size(mode, len(selected))))
    prefix = _section_prefix(mode)
    sections: list[ReasonOutputSection] = []
    offset = 0
    total_steps = len(selected)
    for index, batch in enumerate(batches):
        start_index = offset
        end_index = offset + len(batch) - 1
        offset += len(batch)
        lead = _shorten(batch[0].summary)
        tail = _shorten(batch[-1].summary)
        title = f"{prefix} {index + 1}: {lead}"
        if len(batch) > 1 and tail != lead:
            title = f"{prefix} {index + 1}: {lead} → {tail}"
        focus = f"Keep the section anchored to steps {start_index + 1}-{end_index + 1} of {total_steps}."
        if index == 0:
            focus += f" Establish the long-form voice for {thread.topic}."
        elif index == len(batches) - 1:
            focus += " Close the arc cleanly and preserve continuity with earlier sections."
        else:
            focus += " Preserve continuity with the sections before and after it."
        sections.append(
            ReasonOutputSection(
                index=index,
                title=title,
                focus=focus,
                step_ids=tuple(step.id for step in batch),
                source_start_index=start_index,
                source_end_index=end_index,
                summary=f"{lead} → {tail}" if tail != lead else lead,
            )
        )
    return tuple(sections)


def _section_window_size(mode: str, item_count: int) -> int:
    if item_count <= 0:
        return 1
    return min(
        item_count,
        {
            "summary": 12,
            "outline": 6,
            "report": 8,
            "narrative": 8,
        }.get(mode, 8),
    )


def _section_for_position(
    section_plan: Sequence[ReasonOutputSection],
    position: int,
) -> ReasonOutputSection:
    if not section_plan:
        raise ValueError("section plan must not be empty")
    if position < 0:
        return section_plan[0]
    for section in section_plan:
        if section.source_start_index <= position <= section.source_end_index:
            return section
    return section_plan[-1]


def _section_prefix(mode: str) -> str:
    return {
        "narrative": "Chapter",
        "outline": "Section",
        "report": "Section",
        "summary": "Digest",
    }.get(mode, "Section")


def _shorten(text: str, *, limit: int = 42) -> str:
    return textwrap.shorten(" ".join(text.split()), width=limit, placeholder="...")


def _select_steps(steps: Sequence[ReasoningStep], *, start_index: int, end_index: int | None) -> list[ReasoningStep]:
    start = _validate_non_negative_int(start_index, label="start_index")
    if end_index is None:
        return list(steps[start:])
    end = _validate_non_negative_int(end_index, label="end_index")
    if end < start:
        raise ValueError("end_index must be greater than or equal to start_index")
    return list(steps[start : end + 1])





def _chunk_count(item_count: int, size: int) -> int:
    if item_count <= 0:
        return 0
    return (item_count + size - 1) // size


def _chunk_filename(index: int) -> str:
    return f"chunk-{index + 1:03d}.md"


def _export_job_id(
    thread_id: str,
    *,
    mode: str,
    output_format: str,
    start_index: int,
    end_index: int | None,
    segment_size: int,
    source_step_ids: Sequence[str],
) -> str:
    payload = json.dumps(
        {
            "thread_id": thread_id,
            "mode": mode,
            "output_format": output_format,
            "start_index": start_index,
            "end_index": end_index,
            "segment_size": segment_size,
            "source_step_ids": list(source_step_ids),
            "nonce": uuid4().hex,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"reason-output-{digest}"


def _clear_job_artifacts(paths: ReasonOutputPaths) -> None:
    """Remove all job artifact files under the export root.

    The queue is no longer file-based, so there are no queue/processing/
    failed directories to preserve.
    """
    root = paths.root
    if not root.exists():
        return
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _validate_choice(value: str, allowed: Sequence[str], *, label: str) -> str:
    choice = value.strip()
    if choice not in allowed:
        raise ValueError(f"invalid {label}: {value}")
    return choice


def _validate_positive_int(value: object, *, label: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < 1:  # type: ignore[comparison-overlap]
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


def _validate_non_negative_int(value: object, *, label: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < 0:  # type: ignore[comparison-overlap]
        raise ValueError(f"{label} must be a non-negative integer")
    return int(value)


def _validate_segment(value: str, label: str) -> None:
    if value == "" or "/" in value or value in {".", ".."}:
        raise ValueError(f"invalid {label}: {value}")
