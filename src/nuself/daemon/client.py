"""Client for the local NuSelf daemon."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import cast

from nuself.config import runtime_paths
from nuself.daemon.protocol import DaemonRequest, DaemonResponse, JsonValue, RequestType
from nuself.logs import LogEvent


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
        raise DaemonConnectionError(
            f"daemon socket does not exist: {paths.socket_path}"
        )

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


def open_activity(
    turn_id: str,
    *,
    project_root: Path | None = None,
) -> str:
    """Open one turn-scoped daemon activity subscription."""

    response = request(
        "activity_open",
        {"turn_id": turn_id},
        project_root=project_root,
    )
    subscription_id = response.payload.get("subscription_id")
    if response.status != "ok" or not isinstance(subscription_id, str):
        raise DaemonConnectionError(
            response.error or "daemon did not open activity subscription"
        )
    return subscription_id


def next_activity(
    subscription_id: str,
    *,
    project_root: Path | None = None,
    timeout_ms: int = 200,
    limit: int = 50,
) -> tuple[LogEvent, ...]:
    """Long-poll the next bounded activity batch."""

    response = request(
        "activity_next",
        {
            "subscription_id": subscription_id,
            "timeout_ms": timeout_ms,
            "limit": limit,
        },
        project_root=project_root,
        timeout=max(1.0, timeout_ms / 1000 + 0.5),
    )
    if response.status != "ok":
        raise DaemonConnectionError(
            response.error or "daemon activity subscription failed"
        )
    raw_events = response.payload.get("events")
    if not isinstance(raw_events, list):
        raise DaemonConnectionError("daemon activity response is malformed")
    events: list[LogEvent] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            raise DaemonConnectionError("daemon activity event is malformed")
        try:
            events.append(LogEvent.from_record(cast(dict[str, object], raw_event)))
        except ValueError as exc:
            raise DaemonConnectionError("daemon activity event is malformed") from exc
    return tuple(events)


def close_activity(
    subscription_id: str,
    *,
    project_root: Path | None = None,
) -> bool:
    """Close a daemon activity subscription."""

    response = request(
        "activity_close",
        {"subscription_id": subscription_id},
        project_root=project_root,
    )
    return response.status == "ok" and response.payload.get("closed") is True


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
