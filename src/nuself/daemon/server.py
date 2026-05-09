"""Local Unix-socket daemon server."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import socketserver
import threading
import time
from typing import override

from nuself.agent.chat import ChatAgent
from nuself.config import config_int, ensure_runtime_dirs, runtime_paths
from nuself.daemon.protocol import DaemonRequest, DaemonResponse, JsonValue, ProtocolError
from nuself.logs import write_log_event
from nuself.memory.curator import MemoryCurator, MemoryCuratorResult
from nuself.reflection import ReflectionScheduler

DEFAULT_MEMORY_CURATOR_INTERVAL_SECONDS = 300


class DaemonState:
    """Mutable daemon state shared by request handlers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.shutdown_requested = threading.Event()
        self.chat_agent = ChatAgent(project_root)
        self.memory_curator = MemoryCurator(project_root)
        self.memory_curator_interval_seconds = config_int(
            "NUSELF_MEMORY_CURATOR_INTERVAL_SECONDS",
            DEFAULT_MEMORY_CURATOR_INTERVAL_SECONDS,
            project_root,
        )
        self._memory_curator_thread: threading.Thread | None = None
        self.reflection_scheduler = ReflectionScheduler(project_root)
        self.reflection_check_interval_seconds = config_int(
            "NUSELF_REFLECTION_CHECK_INTERVAL_SECONDS",
            60,
            project_root,
        )
        self._reflection_scheduler_thread: threading.Thread | None = None

    def start_background_memory_curator(self) -> None:
        if self._memory_curator_thread is not None:
            return
        self._memory_curator_thread = threading.Thread(
            target=self._run_background_memory_curator,
            name="nuself-memory-curator",
            daemon=True,
        )
        self._memory_curator_thread.start()

    def stop_background_memory_curator(self) -> None:
        if self._memory_curator_thread is not None:
            self._memory_curator_thread.join(timeout=1.0)

    def _run_background_memory_curator(self) -> None:
        while not self.shutdown_requested.wait(self.memory_curator_interval_seconds):
            try:
                self.memory_curator.run_once()
            except RuntimeError:
                continue

    def start_background_reflection_scheduler(self) -> None:
        if self._reflection_scheduler_thread is not None:
            return
        self._reflection_scheduler_thread = threading.Thread(
            target=self._run_background_reflection_scheduler,
            name="nuself-reflection-scheduler",
            daemon=True,
        )
        self._reflection_scheduler_thread.start()

    def stop_background_reflection_scheduler(self) -> None:
        if self._reflection_scheduler_thread is not None:
            self._reflection_scheduler_thread.join(timeout=1.0)

    def _run_background_reflection_scheduler(self) -> None:
        while not self.shutdown_requested.wait(self.reflection_check_interval_seconds):
            try:
                if self.reflection_scheduler.should_reflect():
                    self.reflection_scheduler.reflect()
            except RuntimeError:
                continue


class NuSelfUnixServer(socketserver.ThreadingUnixStreamServer):
    """Unix stream server with typed NuSelf state."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: str, handler: type[socketserver.BaseRequestHandler], state: DaemonState) -> None:
        self.state = state
        super().__init__(socket_path, handler)


class RequestHandler(socketserver.StreamRequestHandler):
    """Handle one JSONL request per client connection."""

    @override
    def handle(self) -> None:
        raw_line = self.rfile.readline()
        request_id = "unknown"
        try:
            daemon_request = DaemonRequest.from_json_line(raw_line)
            request_id = daemon_request.request_id
            response = handle_request(daemon_request, self._daemon_state())
        except ProtocolError as exc:
            response = DaemonResponse.fail(request_id, str(exc))
        self.wfile.write(response.to_json_line())

    def _daemon_state(self) -> DaemonState:
        server = self.server
        if not isinstance(server, NuSelfUnixServer):
            raise RuntimeError("unexpected server type")
        return server.state


def handle_request(request: DaemonRequest, state: DaemonState) -> DaemonResponse:
    """Handle a typed daemon request."""

    if request.type == "ping":
        return DaemonResponse.ok(request, {"message": "pong"})
    if request.type == "echo":
        return DaemonResponse.ok(request, request.payload)
    if request.type == "chat":
        message = request.payload.get("message")
        if not isinstance(message, str):
            write_log_event(
                "daemon",
                "request_failed",
                "chat request rejected",
                project_root=state.project_root,
                level="warning",
                request_id=request.request_id,
                status="error",
                error="chat request requires string payload field 'message'",
            )
            return DaemonResponse.fail(request.request_id, "chat request requires string payload field 'message'")
        thread_id_raw = request.payload.get("thread_id")
        thread_id = thread_id_raw if isinstance(thread_id_raw, str) else "default"
        started_at = time.monotonic()
        try:
            result = state.chat_agent.respond(message, thread_id=thread_id)
            memory_update = _run_memory_curator_once(state.memory_curator)
        except RuntimeError as exc:
            write_log_event(
                "chat",
                "turn_failed",
                "daemon chat turn failed",
                project_root=state.project_root,
                level="error",
                request_id=request.request_id,
                thread_id=thread_id,
                status="error",
                error=str(exc),
            )
            return DaemonResponse.fail(request.request_id, str(exc))
        duration_ms = int((time.monotonic() - started_at) * 1000)
        payload: dict[str, JsonValue] = {
            "answer": result.answer,
            "reply": result.reply,
            "thread_id": result.thread_id,
            "evidence_references": list(result.evidence_references),
            "epistemic_status": result.epistemic_status,
        }
        if result.confidence is not None:
            payload["confidence"] = result.confidence
        if memory_update is not None and memory_update.changed:
            payload["memory_update"] = memory_update.summary()
        write_log_event(
            "chat",
            "turn_completed",
            "daemon chat turn completed",
            project_root=state.project_root,
            request_id=request.request_id,
            thread_id=result.thread_id,
            duration_ms=duration_ms,
            status="ok",
            metadata={
                "evidence_references": len(result.evidence_references),
                "memory_changed": memory_update.changed if memory_update is not None else False,
            },
        )
        return DaemonResponse.ok(request, payload)
    if request.type == "shutdown":
        write_log_event(
            "daemon",
            "shutdown_requested",
            "daemon shutdown requested",
            project_root=state.project_root,
            request_id=request.request_id,
        )
        state.shutdown_requested.set()
        return DaemonResponse.ok(request, {"message": "shutdown requested"})
    return DaemonResponse.fail(request.request_id, f"unsupported request type: {request.type}")


def _run_memory_curator_once(memory_curator: MemoryCurator) -> MemoryCuratorResult | None:
    try:
        return memory_curator.run_once()
    except RuntimeError:
        return None


def run_daemon(project_root: Path | None = None) -> int:
    """Run the local daemon until a shutdown request is received."""

    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    if paths.socket_path.exists():
        paths.socket_path.unlink()
    paths.pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    state = DaemonState(paths.project_root)
    try:
        write_log_event("daemon", "started", "daemon started", project_root=paths.project_root)
        state.start_background_memory_curator()
        state.start_background_reflection_scheduler()
        with NuSelfUnixServer(str(paths.socket_path), RequestHandler, state) as server:
            server.timeout = 0.2
            while not state.shutdown_requested.is_set():
                server.handle_request()
    finally:
        write_log_event("daemon", "stopped", "daemon stopped", project_root=paths.project_root)
        state.stop_background_memory_curator()
        state.stop_background_reflection_scheduler()
        if paths.socket_path.exists():
            paths.socket_path.unlink()
        if paths.pid_path.exists():
            paths.pid_path.unlink()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nuself.daemon.server")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args(argv)
    return run_daemon(args.project_root)


if __name__ == "__main__":
    raise SystemExit(main())
