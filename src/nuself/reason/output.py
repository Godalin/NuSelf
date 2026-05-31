"""Reason output composition service and export job storage."""


from __future__ import annotations

from typing import Sequence
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import json
import subprocess
import shutil
import textwrap
from typing import cast, Callable

from nuself.logs import write_log_event
from nuself.reason.domain import ReasoningStep, ReasoningThread, partition_steps
from nuself.reason.repository import ReasonNotFound
from nuself.reason.service import ReasonService
from nuself.workspace import PrivateWorkspaceStore

REASON_OUTPUT_STORAGE_VERSION = "NuSelfReasonOutput/v1"
REASON_OUTPUT_MODES: tuple[str, ...] = ("outline", "narrative", "report", "summary")
REASON_OUTPUT_FORMATS: tuple[str, ...] = ("markdown",)


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ReasonOutputSection:
    index: int
    title: str
    focus: str
    step_ids: tuple[str, ...]
    source_start_index: int
    source_end_index: int
    summary: str
    created_at: str = field(default_factory=_now_iso)

    def to_wire(self) -> dict[str, object]:
        return {
            "index": self.index,
            "title": self.title,
            "focus": self.focus,
            "step_ids": list(self.step_ids),
            "source_start_index": self.source_start_index,
            "source_end_index": self.source_end_index,
            "summary": self.summary,
            "created_at": self.created_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasonOutputSection:
        return cls(
            index=_expect_int(data, "index"),
            title=_expect_str(data, "title"),
            focus=_expect_str(data, "focus"),
            step_ids=tuple(str(item) for item in _expect_list(data, "step_ids") if isinstance(item, str)),
            source_start_index=_expect_int(data, "source_start_index"),
            source_end_index=_expect_int(data, "source_end_index"),
            summary=_expect_str(data, "summary"),
            created_at=_optional_str(data, "created_at") or _now_iso(),
        )


@dataclass(frozen=True)
class ReasonOutputChunk:
    index: int
    filename: str
    step_ids: tuple[str, ...]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_wire(self) -> dict[str, object]:
        return {
            "index": self.index,
            "filename": self.filename,
            "step_ids": list(self.step_ids),
            "created_at": self.created_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasonOutputChunk:
        return cls(
            index=_expect_int(data, "index"),
            filename=_expect_str(data, "filename"),
            step_ids=tuple(str(item) for item in _expect_list(data, "step_ids") if isinstance(item, str)),
            created_at=_optional_str(data, "created_at") or _now_iso(),
        )


@dataclass(frozen=True)
class ReasonOutputManifest:
    job_id: str
    thread_id: str
    mode: str
    output_format: str
    source_start_index: int
    source_end_index: int | None
    source_step_ids: tuple[str, ...]
    segment_size: int
    status: str = "planned"
    combined_filename: str = "combined.md"
    progress_filename: str = "progress.json"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    sections: tuple[ReasonOutputSection, ...] = ()
    chunks: tuple[ReasonOutputChunk, ...] = ()

    def to_wire(self) -> dict[str, object]:
        return {
            "schema": REASON_OUTPUT_STORAGE_VERSION,
            "job_id": self.job_id,
            "thread_id": self.thread_id,
            "mode": self.mode,
            "output_format": self.output_format,
            "source_start_index": self.source_start_index,
            "source_end_index": self.source_end_index,
            "source_step_ids": list(self.source_step_ids),
            "segment_size": self.segment_size,
            "status": self.status,
            "combined_filename": self.combined_filename,
            "progress_filename": self.progress_filename,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "sections": [section.to_wire() for section in self.sections],
            "chunks": [chunk.to_wire() for chunk in self.chunks],
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasonOutputManifest:
        return cls(
            job_id=_expect_str(data, "job_id"),
            thread_id=_expect_str(data, "thread_id"),
            mode=_expect_str(data, "mode"),
            output_format=_expect_str(data, "output_format"),
            source_start_index=_expect_int(data, "source_start_index"),
            source_end_index=_optional_int(data, "source_end_index"),
            source_step_ids=tuple(str(item) for item in _expect_list(data, "source_step_ids") if isinstance(item, str)),
            segment_size=_expect_int(data, "segment_size"),
            status=_optional_str(data, "status") or "planned",
            combined_filename=_optional_str(data, "combined_filename") or "combined.md",
            progress_filename=_optional_str(data, "progress_filename") or "progress.json",
            created_at=_optional_str(data, "created_at") or _now_iso(),
            updated_at=_optional_str(data, "updated_at") or _now_iso(),
            sections=tuple(
                ReasonOutputSection.from_wire(cast(dict[str, object], section))
                for section in _expect_list(data, "sections")
                if isinstance(section, dict)
            ) if "sections" in data else (),
            chunks=tuple(
                ReasonOutputChunk.from_wire(cast(dict[str, object], chunk))
                for chunk in _expect_list(data, "chunks")
                if isinstance(chunk, dict)
            ),
        )

    def with_updates(self, **changes: object) -> ReasonOutputManifest:
        payload = self.to_wire()
        payload.update(changes)
        payload["updated_at"] = _now_iso()
        # Normalize chunks to a list of wire-form dicts if present
        if "sections" in payload:
            raw_sections = cast(Sequence[object], payload.get("sections"))
            if isinstance(raw_sections, (list, tuple)):
                normalized_sections: list[object] = []
                for item in raw_sections:
                    if isinstance(item, ReasonOutputSection):
                        normalized_sections.append(item.to_wire())
                    elif isinstance(item, dict):
                        normalized_sections.append(cast(dict[str, object], item))
                payload["sections"] = normalized_sections
        if "chunks" in payload:
            raw_chunks = cast(Sequence[object], payload.get("chunks"))
            if isinstance(raw_chunks, (list, tuple)):
                normalized: list[object] = []
                for item in raw_chunks:
                    if isinstance(item, ReasonOutputChunk):
                        normalized.append(item.to_wire())
                    elif isinstance(item, dict):
                        normalized.append(cast(dict[str, object], item))
                payload["chunks"] = normalized
        return ReasonOutputManifest.from_wire(payload)


@dataclass(frozen=True)
class ReasonOutputPaths:
    root: Path
    manifest: Path
    progress: Path
    combined: Path
    pdf: Path
    chunks_dir: Path


class ReasonOutputService:
    """Plan, compose, and persist reason-scoped long-form export jobs."""

    def __init__(
        self,
        project_root: Path | None = None,
        reason_service: ReasonService | None = None,
        workspace_store: PrivateWorkspaceStore | None = None,
    ) -> None:
        self._reason_service = reason_service or ReasonService(project_root)
        self._project_root = project_root or self._reason_service._project_root  # pyright: ignore[reportPrivateUsage]
        self._workspace_store = workspace_store or PrivateWorkspaceStore(self._project_root, scope="reason")

    def list_jobs(self, thread_id: str) -> list[ReasonOutputManifest]:
        root = self._export_root(thread_id)
        if not root.exists():
            return []
        root_manifest = root / "manifest.json"
        if root_manifest.exists():
            manifest = self._read_manifest(root_manifest)
            if manifest is not None:
                return [manifest]
        jobs: list[ReasonOutputManifest] = []
        for path in sorted(root.glob("*/manifest.json")):
            manifest = self._read_manifest(path)
            if manifest is not None:
                jobs.append(manifest)
        return sorted(jobs, key=lambda manifest: (manifest.created_at, manifest.job_id))

    def get_job(self, thread_id: str, job_id: str) -> ReasonOutputManifest:
        root = self._export_root(thread_id)
        root_manifest = root / "manifest.json"
        if root_manifest.exists():
            manifest = self._read_manifest(root_manifest)
            if manifest is not None:
                if manifest.job_id == job_id:
                    return manifest
                raise ReasonNotFound(job_id)
        for path in sorted(root.glob("*/manifest.json")):
            manifest = self._read_manifest(path)
            if manifest is not None and manifest.job_id == job_id:
                return manifest
        raise ReasonNotFound(job_id)

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
        sections = _plan_sections(thread, list(selected), mode=mode)
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
        existing = self._read_manifest(paths.manifest)
        if existing is not None and existing.job_id == job_id:
            queue_path = paths.root / "queue" / f"{job_id}.json"
            if existing.status != "complete" and not queue_path.exists():
                queue_path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(
                    queue_path,
                    {
                        "type": "reason_output_job",
                        "job_id": job_id,
                        "thread_id": thread.id,
                        "manifest": str(paths.manifest),
                        "created_at": existing.created_at,
                        "attempts": 0,
                    },
                )
            return existing

        _clear_job_artifacts(paths)
        paths.root.mkdir(parents=True, exist_ok=True)
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
            {
                "job_id": job_id,
                "thread_id": thread.id,
                "status": manifest.status,
                "completed_chunks": [],
                "total_chunks": _chunk_count(len(selected), segment_size),
                "pdf_status": "pending",
                "pdf_path": None,
                "updated_at": manifest.updated_at,
            },
        )
        write_log_event(
            "reasoning",
            "reason_output_planned",
            f"Planned reason output job {job_id} for thread {thread.id}",
            project_root=self._project_root,
            status="created",
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

        # Enqueue a file-queue event so a background daemon can pick up this job.
        try:
            queue_dir = paths.root / "queue"
            queue_dir.mkdir(parents=True, exist_ok=True)
            event = {
                "type": "reason_output_job",
                "job_id": job_id,
                "thread_id": thread.id,
                "manifest": str(paths.manifest),
                "created_at": manifest.created_at,
                "attempts": 0,
            }
            write_json_atomic(queue_dir / f"{job_id}.json", cast(dict[str, object], event))
            write_log_event(
                "daemon",
                "export_job_enqueued",
                f"Enqueued export job {job_id} for thread {thread.id}",
                project_root=self._project_root,
                status="queued",
                metadata={"thread_id": thread.id, "job_id": job_id, "manifest": str(paths.manifest)},
            )
        except Exception:
            # Queue failures should not break planning; log and continue.
            write_log_event(
                "daemon",
                "export_job_enqueue_failed",
                f"Failed to enqueue export job {job_id} for thread {thread.id}",
                project_root=self._project_root,
                level="warning",
                status="error",
                metadata={"thread_id": thread.id, "job_id": job_id},
            )
        return manifest

    def compose_job(self, thread_id: str, job_id: str) -> ReasonOutputManifest:
        manifest = self.get_job(thread_id, job_id)
        thread = self._reason_service.show_thread(thread_id)
        step_map = {step.id: step for step in self._reason_service.list_steps(thread.id)}
        selected = [step_map[step_id] for step_id in manifest.source_step_ids if step_id in step_map]
        if len(selected) != len(manifest.source_step_ids):
            raise RuntimeError("Cannot compose export job: one or more source steps are missing")

        paths = self._job_paths(thread.id, job_id)
        paths.root.mkdir(parents=True, exist_ok=True)
        chunks: list[ReasonOutputChunk] = []
        section_plan = self._resolve_section_plan(thread, manifest, selected)
        batch_start = 0
        for index, batch in enumerate(partition_steps(selected, manifest.segment_size)):
            section = _section_for_position(section_plan, batch_start)
            chunk = ReasonOutputChunk(index=index, filename=_chunk_filename(index), step_ids=tuple(step.id for step in batch))
            chunk_path = paths.chunks_dir / chunk.filename
            if not chunk_path.exists():
                chunk_path.write_text(
                    _render_chunk_document(
                        thread,
                        manifest,
                        section=section,
                        section_plan=section_plan,
                        body=_render_chunk(thread, manifest, batch, index=index, total=_chunk_count(len(selected), manifest.segment_size)),
                    ),
                    encoding="utf-8",
                )
            chunks.append(chunk)
            batch_start += len(batch)

        return self._finalize_job(thread, manifest, paths, chunks, section_plan)

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
        paths.root.mkdir(parents=True, exist_ok=True)
        chunks: list[ReasonOutputChunk] = []
        section_plan = self._resolve_section_plan(thread, manifest, selected)
        total = _chunk_count(len(selected), manifest.segment_size)
        batch_start = 0
        for index, batch in enumerate(partition_steps(selected, manifest.segment_size)):
            section = _section_for_position(section_plan, batch_start)
            filename = _chunk_filename(index)
            chunk_path = paths.chunks_dir / filename
            # Emit chunk-level start event
            write_log_event(
                "reasoning",
                "reason_output_chunk_started",
                f"Starting chunk {index+1}/{total} for job {manifest.job_id}",
                project_root=self._project_root,
                metadata={"thread_id": thread.id, "job_id": manifest.job_id, "chunk_index": index},
            )

            # Runner composes the chunk text (e.g., via a subagent/LLM)
            try:
                start_ts = datetime.now(UTC).timestamp()
                composed_text = runner(thread, manifest, batch, section=section, section_plan=section_plan, index=index, total=total)
                duration_ms = int((datetime.now(UTC).timestamp() - start_ts) * 1000)
            except Exception as exc:
                # Log failure for this chunk and re-raise to allow caller to handle
                write_log_event(
                    "reasoning",
                    "reason_output_chunk_failed",
                    f"Chunk {index+1}/{total} failed for job {manifest.job_id}: {str(exc)}",
                    project_root=self._project_root,
                    level="error",
                    status="error",
                    error=str(exc),
                    metadata={"thread_id": thread.id, "job_id": manifest.job_id, "chunk_index": index},
                )
                raise

            # persist chunk
            chunk_path.write_text(
                _render_chunk_document(
                    thread,
                    manifest,
                    section=section,
                    section_plan=section_plan,
                    body=composed_text,
                ),
                encoding="utf-8",
            )

            # Emit chunk completed event
            write_log_event(
                "reasoning",
                "reason_output_chunk_completed",
                f"Completed chunk {index+1}/{total} for job {manifest.job_id}",
                project_root=self._project_root,
                status="ok",
                duration_ms=duration_ms,
                metadata={"thread_id": thread.id, "job_id": manifest.job_id, "chunk_index": index, "chunk_path": str(chunk_path)},
            )
            chunk = ReasonOutputChunk(index=index, filename=filename, step_ids=tuple(step.id for step in batch))
            chunks.append(chunk)
            batch_start += len(batch)

        return self._finalize_job(thread, manifest, paths, chunks, section_plan)

    def job_paths(self, thread_id: str, job_id: str) -> ReasonOutputPaths:
        return self._job_paths(thread_id, job_id)

    def _job_paths(self, thread_id: str, job_id: str) -> ReasonOutputPaths:
        _validate_segment(thread_id, "thread id")
        _validate_segment(job_id, "job id")
        workspace = self._workspace_store.ensure(thread_id)
        root = workspace.artifacts / "export"
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
        return workspace.artifacts / "export"

    def _finalize_job(
        self,
        thread: ReasoningThread,
        manifest: ReasonOutputManifest,
        paths: ReasonOutputPaths,
        chunks: Sequence[ReasonOutputChunk],
        section_plan: Sequence[ReasonOutputSection],
    ) -> ReasonOutputManifest:
        combined_text = _combine_chunks(thread, manifest, paths, chunks, section_plan=section_plan)
        paths.combined.write_text(combined_text, encoding="utf-8")
        updated = manifest.with_updates(status="complete", chunks=tuple(chunks), sections=section_plan)
        self._write_manifest(paths.manifest, updated)
        pdf_path = self._generate_pdf(paths)
        pdf_status = "generated" if pdf_path is not None else ("skipped" if not paths.pdf.exists() else "generated")
        self._write_progress(
            paths.progress,
            {
                "job_id": manifest.job_id,
                "thread_id": thread.id,
                "status": updated.status,
                "completed_chunks": [chunk.index for chunk in chunks],
                "total_chunks": len(chunks),
                "pdf_status": pdf_status,
                "pdf_path": str(pdf_path) if pdf_path is not None else (str(paths.pdf) if paths.pdf.exists() else None),
                "updated_at": updated.updated_at,
            },
        )
        write_log_event(
            "reasoning",
            "reason_output_composed",
            f"Composed reason output job {manifest.job_id} for thread {thread.id}",
            project_root=self._project_root,
            status="completed",
            metadata={
                "thread_id": thread.id,
                "job_id": manifest.job_id,
                "chunk_count": len(chunks),
                "combined": str(paths.combined),
            },
        )
        return updated

    def _read_manifest(self, path: Path) -> ReasonOutputManifest | None:
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return ReasonOutputManifest.from_wire(cast(dict[str, object], raw))
        except ValueError:
            return None

    def _write_manifest(self, path: Path, manifest: ReasonOutputManifest) -> None:
        write_json_atomic(path, manifest.to_wire())

    def _write_progress(self, path: Path, payload: dict[str, object]) -> None:
        write_json_atomic(path, payload)

    def _resolve_section_plan(
        self,
        thread: ReasoningThread,
        manifest: ReasonOutputManifest,
        selected: Sequence[ReasoningStep],
    ) -> tuple[ReasonOutputSection, ...]:
        if manifest.sections:
            return manifest.sections
        return _plan_sections(thread, list(selected), mode=manifest.mode)

    def _generate_pdf(self, paths: ReasonOutputPaths) -> Path | None:
        script = self._project_root / "scripts" / "mdpdf.sh"
        if not script.is_file() or not paths.combined.is_file():
            return None
        try:
            subprocess.run(["bash", str(script), str(paths.combined)], cwd=self._project_root, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            write_log_event(
                "reasoning",
                "reason_output_pdf_failed",
                f"Failed to generate PDF for {paths.combined.name}",
                project_root=self._project_root,
                level="warning",
                status="error",
                error=exc.stderr.strip() or exc.stdout.strip() or str(exc),
                metadata={"combined": str(paths.combined), "pdf": str(paths.pdf)},
            )
            return None
        if paths.pdf.is_file():
            write_log_event(
                "reasoning",
                "reason_output_pdf_created",
                f"Generated PDF for {paths.combined.name}",
                project_root=self._project_root,
                status="completed",
                metadata={"combined": str(paths.combined), "pdf": str(paths.pdf)},
            )
            return paths.pdf
        return None


def _render_chunk(
    thread: ReasoningThread,
    manifest: ReasonOutputManifest,
    steps: Sequence[ReasoningStep],
    *,
    index: int,
    total: int,
) -> str:
    heading = {
        "outline": "Outline",
        "summary": "Summary",
        "report": "Report",
        "narrative": "Narrative",
    }[manifest.mode]
    lines = [f"# {heading}: {thread.topic}", ""]
    lines.append(f"- thread: {thread.id}")
    lines.append(f"- job: {manifest.job_id}")
    lines.append(f"- chunk: {index + 1}/{total}")
    lines.append("")
    for step in steps:
        lines.append(f"## {step.summary}")
        lines.append(f"- step_id: {step.id}")
        lines.append(f"- kind: {step.kind}")
        if step.output:
            lines.append("")
            lines.append(step.output)
        elif step.delta:
            lines.append("")
            lines.append(step.delta)
        if step.evidence_refs:
            lines.append("")
            lines.append("Evidence:")
            lines.extend(f"- {ref}" for ref in step.evidence_refs)
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
    lines.append(f"- thread: {thread.id}")
    lines.append(f"- job: {manifest.job_id}")
    lines.append(f"- mode: {manifest.mode}")
    lines.append(f"- format: {manifest.output_format}")
    lines.append(f"- sections: {len(section_plan)}")
    lines.append("")
    lines.append("## Composition plan")
    for section in section_plan:
        lines.append(f"- {section.index + 1}. {section.title}: {section.focus}")
    lines.append("")
    for chunk in chunks:
        chunk_path = paths.chunks_dir / chunk.filename
        lines.append(chunk_path.read_text(encoding="utf-8").rstrip())
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
    lines = [f"# {manifest.mode.title()}: {thread.topic}", ""]
    lines.append(f"- thread: {thread.id}")
    lines.append(f"- job: {manifest.job_id}")
    lines.append(f"- section: {section.index + 1}/{len(section_plan)}")
    lines.append(f"- title: {section.title}")
    lines.append(f"- focus: {section.focus}")
    lines.append(f"- step_range: {section.source_start_index + 1}-{section.source_end_index + 1}")
    lines.append("")
    lines.append("## Composition plan")
    for planned in section_plan:
        marker = " (current)" if planned.index == section.index else ""
        lines.append(f"- {planned.index + 1}. {planned.title}: {planned.focus}{marker}")
    lines.append("")
    lines.append(f"## {section.title}")
    lines.append("")
    lines.append(body.rstrip())
    return "\n".join(lines).rstrip() + "\n"


def _plan_sections(
    thread: ReasoningThread,
    selected: list[ReasoningStep],
    *,
    mode: str,
) -> tuple[ReasonOutputSection, ...]:
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
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"reason-output-{digest}"


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    """Atomically write a JSON payload to a file using a temp-file + replace strategy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _clear_job_artifacts(paths: ReasonOutputPaths) -> None:
    """Remove job artifact files while preserving queue/processing/failed dirs.

    This prevents data loss when re-planning with different params: pending
    queue events, in-progress worker claims, and historical failure records
    are kept intact.
    """
    root = paths.root
    if not root.exists():
        return
    _KEEP_DIRS = frozenset({"queue", "processing", "failed"})
    for child in root.iterdir():
        if child.name in _KEEP_DIRS:
            continue
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


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string or null")
    return value


def _expect_list(data: dict[str, object], field_name: str) -> list[object]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    return cast(list[object], value)


def _expect_int(data: dict[str, object], field_name: str) -> int:
    value = data.get(field_name)
    if not isinstance(value, int):
        raise ValueError(f"field '{field_name}' must be an integer")
    return value


def _optional_int(data: dict[str, object], field_name: str) -> int | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"field '{field_name}' must be an integer or null")
    return value