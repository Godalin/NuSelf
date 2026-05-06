"""Client for the local NuSelf daemon."""

from __future__ import annotations

from pathlib import Path
import socket

from nuself.config import runtime_paths
from nuself.daemon.protocol import DaemonRequest, DaemonResponse, JsonValue, RequestType


class DaemonConnectionError(ConnectionError):
    """Raised when the daemon socket cannot be reached."""


def request(
    request_type: RequestType,
    payload: dict[str, JsonValue] | None = None,
    *,
    project_root: Path | None = None,
    timeout: float = 2.0,
) -> DaemonResponse:
    """Send one request to the local daemon and return one response."""

    req = DaemonRequest(type=request_type, payload=payload or {})
    paths = runtime_paths(project_root)
    if not paths.socket_path.exists():
        raise DaemonConnectionError(f"daemon socket does not exist: {paths.socket_path}")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(paths.socket_path))
            sock.sendall(req.to_json_line())
            response_line = _recv_line(sock)
    except OSError as exc:
        raise DaemonConnectionError(str(exc)) from exc

    return DaemonResponse.from_json_line(response_line)


def ping(project_root: Path | None = None) -> bool:
    """Return whether the daemon responds to ping."""

    try:
        response = request("ping", project_root=project_root)
    except DaemonConnectionError:
        return False
    return response.status == "ok"


def _recv_line(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    if not chunks:
        raise DaemonConnectionError("daemon closed connection without a response")
    return b"".join(chunks).split(b"\n", 1)[0] + b"\n"
