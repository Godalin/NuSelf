"""Client for the local NuSelf daemon."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from math import isfinite
from pathlib import Path
from typing import Literal, TypeAlias, TypeVar

from nuself.config import runtime_paths
from nuself.daemon.payloads import (
    DaemonIdentityPayload,
    ActivityEventsResponsePayload,
    ActivityOpenResponsePayload,
    ChatRequestPayload,
    ChatResponsePayload,
    EmptyPayload,
    HealthResponsePayload,
)
from nuself.daemon.protocol import (
    DaemonRequest,
    DaemonResponse,
    JsonValue,
    ProtocolError,
    RequestType,
)
from nuself.daemon.transport import read_socket_frame
from nuself.runtime.log_event import LogEvent
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.execution import current_cancellation

PayloadT = TypeVar("PayloadT")
DaemonConnectionPhase: TypeAlias = Literal[
    "connect",
    "request_encode",
    "send",
    "receive",
    "response_decode",
    "response_identity",
    "payload_decode",
    "unknown",
]
_NON_RETRYABLE_PHASES = frozenset({"request_encode", "payload_decode"})
_MAY_HAVE_COMPLETED_PHASES = frozenset(
    {
        "send",
        "receive",
        "response_decode",
        "response_identity",
        "payload_decode",
        "unknown",
    }
)


class DaemonConnectionError(ConnectionError):
    """One structurally classified daemon transport/protocol failure."""

    def __init__(
        self,
        message: str,
        *,
        phase: DaemonConnectionPhase = "unknown",
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.request_id = request_id

    @property
    def retryable(self) -> bool:
        """Return whether an idempotent chat turn may benefit from retry."""

        return self.phase not in _NON_RETRYABLE_PHASES

    @property
    def request_may_have_completed(self) -> bool:
        """Return whether the daemon may already have executed the request."""

        return self.phase in _MAY_HAVE_COMPLETED_PHASES


class DaemonApplicationError(RuntimeError):
    """Raised when the daemon explicitly rejects a valid request."""


class ActivityStreamGapError(DaemonApplicationError):
    """Raised when bounded live activity lost events before delivery."""

    def __init__(self, dropped_count: int) -> None:
        super().__init__(
            f"daemon activity stream dropped {dropped_count} event(s)"
        )
        self.dropped_count = dropped_count


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
            f"daemon socket does not exist: {paths.socket_path}",
            phase="connect",
            request_id=req.request_id,
        )

    phase: DaemonConnectionPhase = "connect"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            cancellation = current_cancellation()

            def close_cancelled_socket() -> None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

            unregister_cancellation = (
                cancellation.register(close_cancelled_socket)
                if cancellation is not None
                else lambda: None
            )
            deadline = time.monotonic() + timeout
            sock.settimeout(
                min(timeout, 0.1)
                if cancellation is not None
                else timeout
            )
            retry_timeout_callback: Callable[[], bool] | None = None
            if cancellation is not None:

                def should_retry_timeout() -> bool:
                    return (
                        not cancellation.cancelled
                        and time.monotonic() < deadline
                    )

                retry_timeout_callback = should_retry_timeout
            try:
                sock.connect(str(paths.socket_path))
                phase = "request_encode"
                request_frame = req.to_json_line()
                phase = "send"
                sock.sendall(request_frame)
                phase = "receive"
                try:
                    response_line = read_socket_frame(
                        sock,
                        retry_timeout=retry_timeout_callback,
                    )
                except ProtocolError:
                    phase = "response_decode"
                    raise
            finally:
                unregister_cancellation()
        phase = "response_decode"
        response = DaemonResponse.from_json_line(response_line)
        phase = "response_identity"
        if response.request_id != req.request_id:
            raise ProtocolError(
                "daemon response request_id does not match request"
            )
        return response
    except (OSError, ProtocolError) as exc:
        detail = diagnostic_exception_message(exc)
        raise DaemonConnectionError(
            detail,
            phase=phase,
            request_id=req.request_id,
        ) from exc


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
            f"daemon {operation} response is malformed: "
            f"{diagnostic_exception_message(exc)}",
            phase="payload_decode",
            request_id=response.request_id,
        ) from exc


def ping(
    project_root: Path | None = None,
    *,
    timeout: float = 2.0,
) -> bool:
    """Return whether the daemon responds to ping."""

    try:
        response = request(
            "ping",
            project_root=project_root,
            timeout=timeout,
        )
        payload = decode_response(
            response,
            DaemonIdentityPayload.from_wire,
            operation="ping",
        )
    except (DaemonConnectionError, DaemonApplicationError):
        return False
    expected_id = runtime_paths(project_root).scope.authority_id
    return payload.authority_id == expected_id


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
    conversation_id: str = "default",
    turn_id: str | None = None,
    project_root: Path | None = None,
    timeout: float,
) -> ChatResponsePayload:
    """Run one chat request and decode its complete success payload."""

    payload = ChatRequestPayload(
        message=message,
        conversation_id=conversation_id,
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
    *,
    timeout: float = 2.0,
) -> None:
    """Request shutdown and validate the acknowledgement payload."""

    response = request(
        "shutdown",
        project_root=project_root,
        timeout=timeout,
    )
    decode_response(
        response,
        EmptyPayload.from_wire,
        operation="shutdown",
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
    if payload.dropped_count:
        raise ActivityStreamGapError(payload.dropped_count)
    return payload.events


def close_activity(
    subscription_id: str,
    *,
    project_root: Path | None = None,
) -> None:
    """Close a daemon activity subscription."""

    response = request(
        "activity_close",
        {"subscription_id": subscription_id},
        project_root=project_root,
    )
    decode_response(
        response,
        EmptyPayload.from_wire,
        operation="activity close",
    )
