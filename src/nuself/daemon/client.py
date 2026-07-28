"""Client for the local NuSelf daemon."""

from __future__ import annotations

import socket
from collections.abc import Callable
from math import isfinite
from pathlib import Path
from typing import TypeVar

from nuself.config import runtime_paths
from nuself.daemon.payloads import (
    ActivityCloseResponsePayload,
    ActivityEventsResponsePayload,
    ActivityOpenResponsePayload,
    ChatRequestPayload,
    ChatResponsePayload,
    HealthResponsePayload,
    MessagePayload,
)
from nuself.daemon.protocol import (
    DaemonRequest,
    DaemonResponse,
    JsonValue,
    ProtocolError,
    RequestType,
)
from nuself.daemon.transport import read_socket_frame
from nuself.logs import LogEvent

PayloadT = TypeVar("PayloadT")


class DaemonConnectionError(ConnectionError):
    """Raised when the daemon socket cannot be reached."""


class DaemonApplicationError(RuntimeError):
    """Raised when the daemon explicitly rejects a valid request."""


def request(
    request_type: RequestType,
    payload: dict[str, JsonValue] | None = None,
    *,
    project_root: Path | None = None,
    timeout: float = 2.0,
) -> DaemonResponse:
    """Send one request to the local daemon and return one response."""

    if (
        isinstance(timeout, bool)
        or not isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("daemon request timeout must be positive and finite")
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
            response_line = read_socket_frame(sock)
        response = DaemonResponse.from_json_line(response_line)
        if response.request_id != req.request_id:
            raise ProtocolError(
                "daemon response request_id does not match request"
            )
        return response
    except (OSError, ProtocolError) as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise DaemonConnectionError(detail) from exc


def decode_response(
    response: DaemonResponse,
    decoder: Callable[[dict[str, JsonValue]], PayloadT],
    *,
    operation: str,
) -> PayloadT:
    """Decode one successful response without conflating daemon failures."""

    if response.status == "error":
        raise DaemonApplicationError(
            response.error or f"daemon {operation} failed"
        )
    try:
        return decoder(response.payload)
    except ProtocolError as exc:
        raise DaemonConnectionError(
            f"daemon {operation} response is malformed: {exc}"
        ) from exc


def ping(project_root: Path | None = None) -> bool:
    """Return whether the daemon responds to ping."""

    try:
        response = request("ping", project_root=project_root)
        payload = decode_response(
            response,
            MessagePayload.from_wire,
            operation="ping",
        )
    except (DaemonConnectionError, DaemonApplicationError):
        return False
    return payload.message == "pong"


def health(
    project_root: Path | None = None,
    *,
    timeout: float = 2.0,
) -> HealthResponsePayload:
    """Return a fully validated daemon worker-health snapshot."""

    return decode_response(
        request(
            "health",
            project_root=project_root,
            timeout=timeout,
        ),
        HealthResponsePayload.from_wire,
        operation="health",
    )


def chat(
    message: str,
    *,
    thread_id: str = "default",
    turn_id: str | None = None,
    project_root: Path | None = None,
    timeout: float,
) -> ChatResponsePayload:
    """Run one chat request and decode its complete success payload."""

    payload = ChatRequestPayload(
        message=message,
        thread_id=thread_id,
        turn_id=turn_id,
    )
    return decode_response(
        request(
            "chat",
            payload.to_wire(),
            project_root=project_root,
            timeout=timeout,
        ),
        ChatResponsePayload.from_wire,
        operation="chat",
    )


def shutdown(
    project_root: Path | None = None,
) -> None:
    """Request shutdown and validate the acknowledgement payload."""

    payload = decode_response(
        request("shutdown", project_root=project_root),
        MessagePayload.from_wire,
        operation="shutdown",
    )
    if payload.message != "shutdown requested":
        raise DaemonConnectionError(
            "daemon shutdown response is malformed: unexpected message"
        )


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
    payload = decode_response(
        response,
        ActivityOpenResponsePayload.from_wire,
        operation="activity open",
    )
    return payload.subscription_id


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
    payload = decode_response(
        response,
        ActivityEventsResponsePayload.from_wire,
        operation="activity next",
    )
    return payload.events


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
    payload = decode_response(
        response,
        ActivityCloseResponsePayload.from_wire,
        operation="activity close",
    )
    return payload.closed
