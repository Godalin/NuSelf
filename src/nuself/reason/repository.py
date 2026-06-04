"""File-backed reasoning repository — ported to StorageBackend."""

from __future__ import annotations

import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from nuself.handles import VisibleHandleError, resolve_visible_item
from nuself.reason.domain import ACTIVE_STATUSES, ReasoningStep, ReasoningThread
from nuself.storage import StorageBackend, auto_backend

REASON_STORAGE_VERSION = "NuSelfReasonStore/v1"

_write_lock = threading.RLock()


class ReasonNotFound(ValueError):
    """Raised when a thread or step cannot be resolved."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"reason not found: {identifier}")


class ReasonRepository:
    """Store reasoning threads and steps via ``StorageBackend``."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
    ) -> None:
        self._project_root = project_root
        effective = backend if backend is not None else auto_backend(project_root)
        self._threads = effective.collection("reason_threads")
        self._steps = effective.collection("reason_steps")

    @property
    def project_root(self) -> Path | None:
        return self._project_root

    @contextmanager
    def batch_write(self) -> Generator[None]:
        """Context manager for atomic multi-file writes (e.g. step + thread)."""
        with _write_lock:
            yield

    def ensure(self) -> None:
        pass  # collections create directories automatically

    # ── Thread operations ──────────────────────────────────────────

    def save_thread(self, thread: ReasoningThread) -> ReasoningThread:
        with _write_lock:
            self._threads.put(thread.id, thread.to_wire())
        return thread

    def get_thread(self, thread_id: str) -> ReasoningThread:
        raw = self._threads.get(thread_id)
        if raw is None:
            raise ReasonNotFound(thread_id)
        return ReasoningThread.from_wire(raw)

    def list_threads(self, status: str | None = "all") -> list[ReasoningThread]:
        threads: list[ReasoningThread] = []
        for raw in self._threads.list():
            try:
                thread = ReasoningThread.from_wire(raw)
            except ValueError:
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
            self._threads.delete(thread_id)
            for raw in self._steps.find(thread_id=thread_id):
                sid = raw.get("id")
                if isinstance(sid, str):
                    self._steps.delete(sid)

    # ── Step operations ────────────────────────────────────────────

    def save_step(self, step: ReasoningStep) -> ReasoningStep:
        with _write_lock:
            self._steps.put(step.id, step.to_wire())
        return step

    def list_steps(self, thread_id: str) -> list[ReasoningStep]:
        steps: list[ReasoningStep] = []
        for raw in self._steps.find(thread_id=thread_id):
            try:
                step = ReasoningStep.from_wire(raw)
            except ValueError:
                continue
            steps.append(step)
        return sorted(steps, key=lambda s: (s.created_at, s.id))

    def get_step(self, step_id: str) -> ReasoningStep:
        raw = self._steps.get(step_id)
        if raw is None:
            raise ReasonNotFound(step_id)
        return ReasoningStep.from_wire(raw)

    # ── Index ──────────────────────────────────────────────────────

    def reindex(self) -> Path:
        return Path("_reindexed_")
