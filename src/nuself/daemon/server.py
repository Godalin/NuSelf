"""Local Unix-socket daemon server."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import socketserver
import threading
from typing import override

from nuself.agent.chat import ChatAgent
from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.daemon.protocol import DaemonRequest, DaemonResponse, ProtocolError


class DaemonState:
    """Mutable daemon state shared by request handlers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.shutdown_requested = threading.Event()
        self.chat_agent = ChatAgent(project_root)


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
            return DaemonResponse.fail(request.request_id, "chat request requires string payload field 'message'")
        try:
            result = state.chat_agent.respond(message)
        except RuntimeError as exc:
            return DaemonResponse.fail(request.request_id, str(exc))
        return DaemonResponse.ok(
            request,
            {
                "reply": result.reply,
                "thread_id": result.thread_id,
            },
        )
    if request.type == "shutdown":
        state.shutdown_requested.set()
        return DaemonResponse.ok(request, {"message": "shutdown requested"})
    return DaemonResponse.fail(request.request_id, f"unsupported request type: {request.type}")


def run_daemon(project_root: Path | None = None) -> int:
    """Run the local daemon until a shutdown request is received."""

    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    if paths.socket_path.exists():
        paths.socket_path.unlink()
    paths.pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    state = DaemonState(paths.project_root)
    try:
        with NuSelfUnixServer(str(paths.socket_path), RequestHandler, state) as server:
            server.timeout = 0.2
            while not state.shutdown_requested.is_set():
                server.handle_request()
    finally:
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
