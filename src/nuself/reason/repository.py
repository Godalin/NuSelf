"""File-backed reasoning repository."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, cast

from nuself.handles import VisibleHandleError, resolve_visible_item
from nuself.config import runtime_paths
from nuself.reason.domain import ACTIVE_STATUSES, ReasoningStep, ReasoningThread

REASON_STORAGE_VERSION = "NuSelfReasonStore/v1"

_write_lock = threading.RLock()


class ReasonNotFound(ValueError):
    """Raised when a thread or step cannot be resolved."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"reason not found: {identifier}")


class ReasonRepository:
    """Store reasoning threads and steps under private/reasoning/."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root
        paths = runtime_paths(project_root)
        self._root = paths.private_root / "reasoning"
        self._threads_dir = self._root / "threads"
        self._steps_dir = self._root / "steps"
        self._index_path = self._root / "index.json"

    @property
    def project_root(self) -> Path | None:
        return self._project_root

    @contextmanager
    def batch_write(self) -> Generator[None]:
        """Context manager for atomic multi-file writes (e.g. step + thread)."""
        with _write_lock:
            yield

    def ensure(self) -> None:
        self._threads_dir.mkdir(parents=True, exist_ok=True)
        self._steps_dir.mkdir(parents=True, exist_ok=True)

    # ── Thread operations ──────────────────────────────────────────

    def save_thread(self, thread: ReasoningThread) -> ReasoningThread:
        with _write_lock:
            self.ensure()
            _write_json_atomic(self._thread_path(thread.id), thread.to_wire())
        return thread

    def get_thread(self, thread_id: str) -> ReasoningThread:
        path = self._thread_path(thread_id)
        if not path.exists():
            raise ReasonNotFound(thread_id)
        return self._read_thread_path(path)

    def list_threads(self, status: str | None = None) -> list[ReasoningThread]:
        self.ensure()
        threads: list[ReasoningThread] = []
        for path in sorted(self._threads_dir.glob("*.json")):
            thread = _safe_read_thread_path(path)
            if thread is None:
                continue
            if status is None:
                if thread.status not in ACTIVE_STATUSES:
                    continue
            elif status != "all" and thread.status != status:
                continue
            threads.append(thread)
        return sorted(threads, key=lambda t: (t.created_at, t.id))

    def resolve_thread(self, id_or_index: str, *, status: str | None = "all") -> ReasoningThread:
        try:
            return self.get_thread(id_or_index)
        except ReasonNotFound:
            pass
        threads = self.list_threads(status=status)
        try:
            thread = resolve_visible_item(id_or_index, threads, label="reason")
        except VisibleHandleError as exc:
            raise ReasonNotFound(id_or_index) from exc
        if thread is None:
            raise ReasonNotFound(id_or_index)
        return thread

    def delete_thread(self, thread_id: str) -> None:
        with _write_lock:
            path = self._thread_path(thread_id)
            if path.exists():
                path.unlink()
            steps_dir = self._steps_dir / thread_id
            if steps_dir.exists():
                import shutil
                shutil.rmtree(steps_dir)

    # ── Step operations ────────────────────────────────────────────

    def save_step(self, step: ReasoningStep) -> ReasoningStep:
        with _write_lock:
            self.ensure()
            thread_steps_dir = self._steps_dir / step.thread_id
            thread_steps_dir.mkdir(parents=True, exist_ok=True)
            _write_json_atomic(thread_steps_dir / f"{step.id}.json", step.to_wire())
        return step

    def list_steps(self, thread_id: str) -> list[ReasoningStep]:
        self.ensure()
        thread_steps_dir = self._steps_dir / thread_id
        if not thread_steps_dir.exists():
            return []
        steps: list[ReasoningStep] = []
        for path in sorted(thread_steps_dir.glob("*.json")):
            step = _safe_read_step_path(path)
            if step is None:
                continue
            steps.append(step)
        return sorted(steps, key=lambda s: (s.created_at, s.id))

    def get_step(self, step_id: str) -> ReasoningStep:
        for thread_dir in sorted(self._steps_dir.glob("*")):
            if not thread_dir.is_dir():
                continue
            path = thread_dir / f"{step_id}.json"
            if path.exists():
                return self._read_step_path(path)
        raise ReasonNotFound(step_id)

    # ── Index ──────────────────────────────────────────────────────

    def reindex(self) -> Path:
        with _write_lock:
            self.ensure()
            threads = [_safe_read_thread_path(path) for path in sorted(self._threads_dir.glob("*.json"))]
            step_ids: dict[str, list[str]] = {}
            total_steps = 0
            for thread_dir in sorted(self._steps_dir.glob("*")):
                if not thread_dir.is_dir():
                    continue
                tid = thread_dir.name
                ids: list[str] = []
                for path in sorted(thread_dir.glob("*.json")):
                    step = _safe_read_step_path(path)
                    if step is not None:
                        ids.append(step.id)
                step_ids[tid] = ids
                total_steps += len(ids)

            trace_ids = [t.id for t in threads if t is not None]
            payload: dict[str, object] = {
                "schema": REASON_STORAGE_VERSION,
                "thread_count": len(trace_ids),
                "step_count": total_steps,
                "thread_ids": trace_ids,
                "step_ids": step_ids,
            }
            _write_json_atomic(self._index_path, payload)
        return self._index_path

    # ── Helpers ────────────────────────────────────────────────────

    def _thread_path(self, thread_id: str) -> Path:
        _validate_id(thread_id, "thread id")
        return self._threads_dir / f"{thread_id}.json"

    def _read_thread_path(self, path: Path) -> ReasoningThread:
        thread = _safe_read_thread_path(path)
        if thread is None:
            raise ValueError(f"invalid thread file: {path}")
        return thread

    def _read_step_path(self, path: Path) -> ReasoningStep:
        step = _safe_read_step_path(path)
        if step is None:
            raise ValueError(f"invalid step file: {path}")
        return step


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _safe_read_thread_path(path: Path) -> ReasoningThread | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ReasoningThread.from_wire(cast(dict[str, object], raw))
    except ValueError:
        return None


def _safe_read_step_path(path: Path) -> ReasoningStep | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ReasoningStep.from_wire(cast(dict[str, object], raw))
    except ValueError:
        return None


def _validate_id(value: str, label: str) -> None:
    if value == "" or "/" in value or value in {".", ".."}:
        raise ValueError(f"invalid {label}: {value}")
