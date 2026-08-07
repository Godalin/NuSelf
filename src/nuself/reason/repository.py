"""SQLite-backed reasoning repository."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Generator

from nuself.runtime.handles import VisibleHandleError, resolve_visible_item
from nuself.config.settings import RuntimePaths
from nuself.reason.model import ACTIVE_STATUSES, ReasoningStep, ReasoningThread
from nuself.reason.errors import ReasonNotFound
from nuself.runtime.observability import decode_observed_record
from nuself.storage.contract import StorageBackend

_write_lock = threading.RLock()


class ReasonRepository:
    """Store reasoning threads and steps via ``StorageBackend``."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        backend: StorageBackend,
    ) -> None:
        self._backend = backend
        self._threads = backend.collection("reason_threads")
        self._steps = backend.collection("reason_steps")
        self._paths = paths

    @contextmanager
    def batch_write(self) -> Generator[None]:
        """Commit a step + thread update as one backend transaction."""
        with _write_lock:
            with self._backend.transaction():
                yield

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
            thread = decode_observed_record(
                raw,
                ReasoningThread.from_wire,
                component="reasoning",
                collection="reason_threads",
                project_root=self._paths.authority_root,
            )
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
            step = decode_observed_record(
                raw,
                ReasoningStep.from_wire,
                component="reasoning",
                collection="reason_steps",
                project_root=self._paths.authority_root,
            )
            if step is None:
                continue
            steps.append(step)
        return sorted(steps, key=lambda s: (s.created_at, s.id))
