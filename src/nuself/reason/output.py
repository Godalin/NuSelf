"""Reason output composition service and export job storage."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import json
from typing import cast
from uuid import uuid4

from nuself.logs import write_log_event
from nuself.reason.domain import ReasoningStep, ReasoningThread
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
        if "chunks" in payload:
            raw_chunks = payload.get("chunks")
            if isinstance(raw_chunks, (list, tuple)):
                normalized: list[object] = []
                for c in raw_chunks:
                    if hasattr(c, "to_wire"):
                        normalized.append(c.to_wire())
                    elif isinstance(c, dict):
                        normalized.append(c)
                payload["chunks"] = normalized
        return ReasonOutputManifest.from_wire(payload)


@dataclass(frozen=True)
class ReasonOutputPaths:
    root: Path
    manifest: Path
    progress: Path
    combined: Path
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
        jobs: list[ReasonOutputManifest] = []
        for path in sorted(root.glob("*/manifest.json")):
            manifest = self._read_manifest(path)
            if manifest is not None:
                jobs.append(manifest)
        return sorted(jobs, key=lambda manifest: (manifest.created_at, manifest.job_id))

    def get_job(self, thread_id: str, job_id: str) -> ReasonOutputManifest:
        path = self._job_paths(thread_id, job_id).manifest
        if not path.exists():
            raise ReasonNotFound(job_id)
        manifest = self._read_manifest(path)
        if manifest is None:
            raise ValueError(f"invalid reason output manifest: {path}")
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
        job_id = _new_job_id()
        paths = self._job_paths(thread.id, job_id)
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
            }
            tmp = queue_dir / f"{job_id}.json.tmp"
            final = queue_dir / f"{job_id}.json"
            tmp.write_text(json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
            tmp.replace(final)
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
        for index, batch in enumerate(_partition(selected, manifest.segment_size)):
            chunk = ReasonOutputChunk(index=index, filename=_chunk_filename(index), step_ids=tuple(step.id for step in batch))
            chunk_path = paths.chunks_dir / chunk.filename
            if not chunk_path.exists():
                chunk_path.write_text(
                    _render_chunk(thread, manifest, batch, index=index, total=_chunk_count(len(selected), manifest.segment_size)),
                    encoding="utf-8",
                )
            chunks.append(chunk)

        combined_text = _combine_chunks(thread, manifest, paths, chunks)
        paths.combined.write_text(combined_text, encoding="utf-8")
        updated = manifest.with_updates(status="complete", chunks=tuple(chunks))
        self._write_manifest(paths.manifest, updated)
        self._write_progress(
            paths.progress,
            {
                "job_id": job_id,
                "thread_id": thread.id,
                "status": updated.status,
                "completed_chunks": [chunk.index for chunk in chunks],
                "total_chunks": len(chunks),
                "updated_at": updated.updated_at,
            },
        )
        write_log_event(
            "reasoning",
            "reason_output_composed",
            f"Composed reason output job {job_id} for thread {thread.id}",
            project_root=self._project_root,
            status="completed",
            metadata={
                "thread_id": thread.id,
                "job_id": job_id,
                "chunk_count": len(chunks),
                "combined": str(paths.combined),
            },
        )
        return updated

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

    def compose_with_runner(self, thread_id: str, job_id: str, runner: callable) -> ReasonOutputManifest:
        """Compose the job using an injected runner callable for each segment.

        The runner callable is invoked for each segment with signature:
            runner(thread: ReasoningThread, manifest: ReasonOutputManifest, steps: Sequence[ReasoningStep], *, index: int, total: int) -> str

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
        total = _chunk_count(len(selected), manifest.segment_size)
        for index, batch in enumerate(_partition(selected, manifest.segment_size)):
            filename = _chunk_filename(index)
            chunk_path = paths.chunks_dir / filename
            # Runner composes the chunk text (e.g., via a subagent/LLM)
            composed_text = runner(thread, manifest, batch, index=index, total=total)
            # persist chunk
            chunk_path.write_text(composed_text.rstrip() + "\n", encoding="utf-8")
            chunk = ReasonOutputChunk(index=index, filename=filename, step_ids=tuple(step.id for step in batch))
            chunks.append(chunk)

        combined_text = _combine_chunks(thread, manifest, paths, chunks)
        paths.combined.write_text(combined_text, encoding="utf-8")
        updated = manifest.with_updates(status="complete", chunks=tuple(chunks))
        self._write_manifest(paths.manifest, updated)
        self._write_progress(
            paths.progress,
            {
                "job_id": job_id,
                "thread_id": thread.id,
                "status": updated.status,
                "completed_chunks": [chunk.index for chunk in chunks],
                "total_chunks": len(chunks),
                "updated_at": updated.updated_at,
            },
        )
        write_log_event(
            "reasoning",
            "reason_output_composed",
            f"Composed reason output job {job_id} for thread {thread.id} via runner",
            project_root=self._project_root,
            status="completed",
            metadata={
                "thread_id": thread.id,
                "job_id": job_id,
                "chunk_count": len(chunks),
                "combined": str(paths.combined),
            },
        )
        return updated

    def job_paths(self, thread_id: str, job_id: str) -> ReasonOutputPaths:
        return self._job_paths(thread_id, job_id)

    def _job_paths(self, thread_id: str, job_id: str) -> ReasonOutputPaths:
        _validate_segment(thread_id, "thread id")
        _validate_segment(job_id, "job id")
        workspace = self._workspace_store.ensure(thread_id)
        root = workspace.artifacts / "export" / job_id
        return ReasonOutputPaths(
            root=root,
            manifest=root / "manifest.json",
            progress=root / "progress.json",
            combined=root / "combined.md",
            chunks_dir=root,
        )

    def _export_root(self, thread_id: str) -> Path:
        workspace = self._workspace_store.ensure(thread_id)
        return workspace.artifacts / "export"

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
        _write_json_atomic(path, manifest.to_wire())

    def _write_progress(self, path: Path, payload: dict[str, object]) -> None:
        _write_json_atomic(path, payload)


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
) -> str:
    lines = [f"# {thread.topic}", ""]
    lines.append(f"- thread: {thread.id}")
    lines.append(f"- job: {manifest.job_id}")
    lines.append(f"- mode: {manifest.mode}")
    lines.append(f"- format: {manifest.output_format}")
    lines.append("")
    for chunk in chunks:
        chunk_path = paths.chunks_dir / chunk.filename
        lines.append(chunk_path.read_text(encoding="utf-8").rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _select_steps(steps: Sequence[ReasoningStep], *, start_index: int, end_index: int | None) -> list[ReasoningStep]:
    start = _validate_non_negative_int(start_index, label="start_index")
    if end_index is None:
        return list(steps[start:])
    end = _validate_non_negative_int(end_index, label="end_index")
    if end < start:
        raise ValueError("end_index must be greater than or equal to start_index")
    return list(steps[start : end + 1])


def _partition(items: Sequence[ReasoningStep], size: int) -> list[list[ReasoningStep]]:
    if size < 1:
        raise ValueError("segment_size must be a positive integer")
    result: list[list[ReasoningStep]] = []
    for index in range(0, len(items), size):
        result.append(list(items[index : index + size]))
    return result


def _chunk_count(item_count: int, size: int) -> int:
    if item_count <= 0:
        return 0
    return (item_count + size - 1) // size


def _chunk_filename(index: int) -> str:
    return f"chunk-{index + 1:03d}.md"


def _new_job_id() -> str:
    return f"reason-output-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _validate_choice(value: str, allowed: Sequence[str], *, label: str) -> str:
    choice = value.strip()
    if choice not in allowed:
        raise ValueError(f"invalid {label}: {value}")
    return choice


def _validate_positive_int(value: int, *, label: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _validate_non_negative_int(value: int, *, label: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


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
    return value


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