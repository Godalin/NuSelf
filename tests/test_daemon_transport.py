from __future__ import annotations

import io
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from nuself.config import runtime_paths
from nuself.daemon import client
from nuself.daemon.client import DaemonConnectionError
from nuself.daemon.client import DaemonApplicationError
from nuself.daemon.client import ActivityStreamGapError
from nuself.daemon.payloads import (
    ActivityEventsResponsePayload,
    MessagePayload,
)
from nuself.daemon.protocol import (
    MAX_DAEMON_FRAME_BYTES,
    DaemonExtraFrameData,
    DaemonFrameTooLarge,
    DaemonIncompleteFrame,
    DaemonPeerDisconnected,
    DaemonRequest,
    DaemonResponse,
    JsonValue,
    ProtocolError,
    RequestType,
)
from nuself.daemon.transport import (
    read_socket_frame,
    read_stream_frame,
    write_stream_frame,
)
from nuself.logs import read_log_events


class ChunkSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def recv(self, size: int) -> bytes:
        del size
        return self._chunks.pop(0) if self._chunks else b""


class PartialWriter:
    def __init__(self, chunk_size: int) -> None:
        self.chunk_size = chunk_size
        self.data = bytearray()
        self.flush_calls = 0

    def write(self, data: bytes) -> int:
        written = min(self.chunk_size, len(data))
        self.data.extend(data[:written])
        return written

    def flush(self) -> None:
        self.flush_calls += 1


class FakeConnection:
    def __init__(self, reader: object) -> None:
        self._reader = reader
        self.timeout: float | None = None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def recv(self, size: int) -> bytes:
        reader = self._reader
        if isinstance(reader, TimeoutReader):
            return reader.recv(size)
        if isinstance(reader, io.BytesIO):
            return reader.read(size)
        raise TypeError("unsupported fake connection reader")


class TimeoutReader:
    def recv(self, size: int) -> bytes:
        del size
        raise socket.timeout("request read timed out")


class BrokenWriter:
    def write(self, data: bytes) -> int:
        del data
        raise BrokenPipeError("client disconnected")

    def flush(self) -> None:
        raise AssertionError("flush must not follow a failed write")


class ClientSocket:
    def __init__(self, response: bytes) -> None:
        self._response = response
        self._sent = False
        self.timeout: float | None = None
        self.sent = b""

    def __enter__(self) -> ClientSocket:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, path: str) -> None:
        assert path

    def sendall(self, data: bytes) -> None:
        self.sent = data

    def recv(self, size: int) -> bytes:
        del size
        if self._sent:
            return b""
        self._sent = True
        return self._response


class SendFailingClientSocket(ClientSocket):
    def sendall(self, data: bytes) -> None:
        del data
        raise BrokenPipeError("request send failed")


class ReceiveFailingClientSocket(ClientSocket):
    def recv(self, size: int) -> bytes:
        del size
        raise socket.timeout("response timed out")


def test_socket_frame_reader_accepts_fragmented_frame() -> None:
    sock = ChunkSocket([b'{"ok":', b"true}\n"])

    assert read_socket_frame(sock) == b'{"ok":true}\n'  # type: ignore[arg-type]


def test_frame_readers_distinguish_clean_and_partial_eof() -> None:
    with pytest.raises(DaemonPeerDisconnected):
        read_socket_frame(ChunkSocket([]))  # type: ignore[arg-type]
    with pytest.raises(DaemonIncompleteFrame):
        read_socket_frame(ChunkSocket([b'{"partial":true}']))  # type: ignore[arg-type]
    with pytest.raises(DaemonPeerDisconnected):
        read_stream_frame(io.BytesIO())
    with pytest.raises(DaemonIncompleteFrame):
        read_stream_frame(io.BytesIO(b'{"partial":true}'))


def test_frame_readers_reject_oversized_and_extra_data() -> None:
    oversized = b"x" * MAX_DAEMON_FRAME_BYTES
    with pytest.raises(DaemonFrameTooLarge):
        read_socket_frame(ChunkSocket([oversized]))  # type: ignore[arg-type]
    with pytest.raises(DaemonFrameTooLarge):
        read_stream_frame(io.BytesIO(oversized))
    with pytest.raises(DaemonExtraFrameData):
        read_socket_frame(  # type: ignore[arg-type]
            ChunkSocket([b'{"one":1}\n{"two":2}\n'])
        )


def test_stream_writer_completes_partial_writes() -> None:
    writer = PartialWriter(chunk_size=3)

    write_stream_frame(writer, b'{"ok":true}\n')  # type: ignore[arg-type]

    assert bytes(writer.data) == b'{"ok":true}\n'
    assert writer.flush_calls == 1


def _handler_fake(
    *,
    project_root: Path,
    raw: object,
    writer: object,
) -> object:
    return SimpleNamespace(
        connection=FakeConnection(raw),
        rfile=raw,
        wfile=writer,
        _daemon_state=lambda: SimpleNamespace(project_root=project_root),
        _request_project_root=lambda: project_root,
    )


def _invalid_success_response(
    daemon_request: DaemonRequest,
    state: object,
) -> DaemonResponse:
    del state
    return DaemonResponse(
        request_id=daemon_request.request_id,
        status="ok",
        error="invalid success",
    )


def test_request_project_root_reads_owned_server_state(tmp_path: Path) -> None:
    from nuself.daemon.socket_server import NuSelfUnixServer, RequestHandler

    server = object.__new__(NuSelfUnixServer)
    server.state = SimpleNamespace(project_root=tmp_path)  # type: ignore[assignment]
    handler = SimpleNamespace(server=server)

    assert RequestHandler._request_project_root(handler) == tmp_path  # type: ignore[arg-type]


def test_request_project_root_omits_unowned_server_state() -> None:
    from nuself.daemon.socket_server import RequestHandler

    handler = SimpleNamespace(
        server=SimpleNamespace(
            state=SimpleNamespace(project_root=Path("/must-not-be-read"))
        )
    )

    assert RequestHandler._request_project_root(handler) is None  # type: ignore[arg-type]


def test_request_project_root_does_not_hide_owned_state_failure() -> None:
    from nuself.daemon.socket_server import NuSelfUnixServer, RequestHandler

    class BrokenState:
        @property
        def project_root(self) -> Path:
            raise RuntimeError("request state is broken")

    server = object.__new__(NuSelfUnixServer)
    server.state = BrokenState()  # type: ignore[assignment]
    handler = SimpleNamespace(server=server)

    with pytest.raises(RuntimeError, match="request state is broken"):
        RequestHandler._request_project_root(handler)  # type: ignore[arg-type]


def test_server_clean_eof_returns_without_response(tmp_path: Path) -> None:
    from nuself.daemon.socket_server import RequestHandler

    writer = io.BytesIO()
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(),
        writer=writer,
    )

    RequestHandler.handle(fake)  # type: ignore[arg-type]

    assert writer.getvalue() == b""
    assert read_log_events(
        project_root=tmp_path,
        component="daemon",
    ) == []


def test_server_incomplete_frame_returns_protocol_failure(
    tmp_path: Path,
) -> None:
    from nuself.daemon.socket_server import RequestHandler

    writer = io.BytesIO()
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(b'{"partial":true}'),
        writer=writer,
    )

    RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(writer.getvalue())
    assert response.status == "error"
    assert response.request_id == "unknown"
    assert response.error == "daemon frame ended before its newline"


def test_server_rejects_second_frame_received_with_request(
    tmp_path: Path,
) -> None:
    from nuself.daemon.socket_server import RequestHandler

    request = DaemonRequest(
        type="ping",
        payload={},
        request_id="first",
    ).to_json_line()
    second = DaemonRequest(
        type="ping",
        payload={},
        request_id="second",
    ).to_json_line()
    writer = io.BytesIO()
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(request + second),
        writer=writer,
    )

    RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(writer.getvalue())
    assert response.status == "error"
    assert response.request_id == "unknown"
    assert response.error == "daemon connection contains more than one frame"


def test_server_read_timeout_is_observed_and_returns_failure(
    tmp_path: Path,
) -> None:
    from nuself.daemon.socket_server import RequestHandler

    writer = io.BytesIO()
    fake = _handler_fake(
        project_root=tmp_path,
        raw=TimeoutReader(),
        writer=writer,
    )

    RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(writer.getvalue())
    assert response.status == "error"
    event = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )[-1]
    assert event.event == "request_transport_failed"
    assert event.error == "request read timed out"


def test_server_sanitizes_unexpected_handler_failure_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.daemon import socket_server as server_module

    request = DaemonRequest(
        type="ping",
        payload={},
        request_id="secret-handler-failure",
    )
    writer = io.BytesIO()
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(request.to_json_line()),
        writer=writer,
    )
    outer_secret = "outer-secret-value"
    root_secret = "root-secret-value"

    def fail_handler(
        _request: DaemonRequest,
        _state: object,
    ) -> DaemonResponse:
        try:
            raise ValueError(f"provider password={root_secret}")
        except ValueError as exc:
            raise RuntimeError(
                f"request failed api_key={outer_secret}"
            ) from exc

    monkeypatch.setattr(server_module, "handle_request", fail_handler)

    server_module.RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(writer.getvalue())
    assert response.error == (
        "request failed api_key=*** <- provider password=***"
    )
    assert outer_secret not in writer.getvalue().decode()
    assert root_secret not in writer.getvalue().decode()
    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.event == "request_failed"
    assert outer_secret not in (event.error or "")
    assert root_secret not in (event.error or "")


def test_server_broken_pipe_is_observed_without_escaping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.daemon import socket_server as server_module

    request = DaemonRequest(
        type="ping",
        payload={},
        request_id="disconnect-request",
    )
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(request.to_json_line()),
        writer=BrokenWriter(),
    )

    def respond(
        daemon_request: DaemonRequest,
        state: object,
    ) -> DaemonResponse:
        del state
        return DaemonResponse.ok(daemon_request)

    monkeypatch.setattr(
        server_module,
        "handle_request",
        respond,
    )

    server_module.RequestHandler.handle(fake)  # type: ignore[arg-type]

    event = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )[-1]
    assert event.event == "response_delivery_failed"
    assert event.request_id == "disconnect-request"
    assert event.error == "client disconnected"


@pytest.mark.parametrize("failure", ["invalid", "oversized"])
def test_server_replaces_unencodable_response_with_failure_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    from nuself.daemon import socket_server as server_module

    request = DaemonRequest(
        type="ping",
        payload={},
        request_id=f"{failure}-response",
    )
    writer = io.BytesIO()
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(request.to_json_line()),
        writer=writer,
    )

    def respond(
        daemon_request: DaemonRequest,
        state: object,
    ) -> DaemonResponse:
        del state
        if failure == "invalid":
            return DaemonResponse(
                request_id=daemon_request.request_id,
                status="ok",
                error="invalid success",
            )
        return DaemonResponse.ok(
            daemon_request,
            {"content": "x" * MAX_DAEMON_FRAME_BYTES},
        )

    monkeypatch.setattr(server_module, "handle_request", respond)

    server_module.RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(writer.getvalue())
    assert response.request_id == request.request_id
    assert response.status == "error"
    assert response.error == "daemon response encoding failed"
    event = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )[-1]
    assert event.event == "response_encode_failed"
    assert event.request_id == request.request_id
    assert event.status == "error"
    assert event.metadata == {"response_status": "ok"}


def test_response_encode_diagnostic_failure_cannot_block_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.daemon import socket_server as server_module

    request = DaemonRequest(
        type="ping",
        payload={},
        request_id="encode-diagnostic-failure",
    )
    writer = io.BytesIO()
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(request.to_json_line()),
        writer=writer,
    )

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("diagnostic store unavailable")

    monkeypatch.setattr(
        server_module,
        "handle_request",
        _invalid_success_response,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        server_module.RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(writer.getvalue())
    assert response.request_id == request.request_id
    assert response.status == "error"
    assert response.error == "daemon response encoding failed"


def test_unencodable_response_fallback_delivery_failure_is_distinct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.daemon import socket_server as server_module

    request = DaemonRequest(
        type="ping",
        payload={},
        request_id="fallback-disconnect",
    )
    fake = _handler_fake(
        project_root=tmp_path,
        raw=io.BytesIO(request.to_json_line()),
        writer=BrokenWriter(),
    )

    monkeypatch.setattr(
        server_module,
        "handle_request",
        _invalid_success_response,
    )

    server_module.RequestHandler.handle(fake)  # type: ignore[arg-type]

    events = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert [event.event for event in events[-2:]] == [
        "response_encode_failed",
        "response_delivery_failed",
    ]
    assert all(
        event.request_id == request.request_id
        for event in events[-2:]
    )
    assert events[-1].error == "client disconnected"
    assert events[-1].metadata == {
        "response_status": "error",
        "fallback": True,
    }


def _prepare_socket_path(project_root: Path) -> None:
    paths = runtime_paths(project_root)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.socket_path.touch()


@pytest.mark.parametrize(
    ("phase", "retryable", "may_have_completed"),
    [
        ("connect", True, False),
        ("request_encode", False, False),
        ("send", True, True),
        ("receive", True, True),
        ("response_decode", True, True),
        ("response_identity", True, True),
        ("payload_decode", False, True),
        ("unknown", True, True),
    ],
)
def test_connection_error_phase_drives_retry_and_completion_state(
    phase: str,
    retryable: bool,
    may_have_completed: bool,
) -> None:
    error = DaemonConnectionError(
        "failed",
        phase=phase,  # type: ignore[arg-type]
        request_id="request-1",
    )

    assert str(error) == "failed"
    assert error.phase == phase
    assert error.request_id == "request-1"
    assert error.retryable is retryable
    assert error.request_may_have_completed is may_have_completed


def test_client_classifies_missing_socket_as_connect_failure(
    tmp_path: Path,
) -> None:
    with pytest.raises(DaemonConnectionError) as captured:
        client.request("ping", project_root=tmp_path)

    assert captured.value.phase == "connect"
    assert captured.value.request_id is not None
    assert captured.value.retryable is True
    assert captured.value.request_may_have_completed is False
    assert captured.value.__cause__ is None


def test_client_request_encoding_failure_is_not_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_socket_path(tmp_path)
    fake_socket = ClientSocket(b"")

    def socket_factory(
        *args: object,
        **kwargs: object,
    ) -> ClientSocket:
        del args, kwargs
        return fake_socket

    monkeypatch.setattr(
        client.socket,
        "socket",
        socket_factory,
    )

    with pytest.raises(DaemonConnectionError) as captured:
        client.request(
            "echo",
            {"value": float("nan")},
            project_root=tmp_path,
        )

    assert captured.value.phase == "request_encode"
    assert captured.value.request_id is not None
    assert captured.value.retryable is False
    assert captured.value.request_may_have_completed is False
    assert isinstance(captured.value.__cause__, ProtocolError)
    assert fake_socket.sent == b""


@pytest.mark.parametrize(
    ("fake_socket", "phase", "message"),
    [
        (
            SendFailingClientSocket(b""),
            "send",
            "request send failed",
        ),
        (
            ReceiveFailingClientSocket(b""),
            "receive",
            "response timed out",
        ),
    ],
)
def test_client_classifies_socket_io_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_socket: ClientSocket,
    phase: str,
    message: str,
) -> None:
    _prepare_socket_path(tmp_path)

    def socket_factory(
        *args: object,
        **kwargs: object,
    ) -> ClientSocket:
        del args, kwargs
        return fake_socket

    monkeypatch.setattr(
        client.socket,
        "socket",
        socket_factory,
    )

    with pytest.raises(DaemonConnectionError) as captured:
        client.request("ping", project_root=tmp_path)

    assert captured.value.phase == phase
    assert captured.value.request_id is not None
    assert captured.value.retryable is True
    assert captured.value.request_may_have_completed is True
    assert message in str(captured.value)
    assert isinstance(captured.value.__cause__, OSError)


def test_client_rejects_mismatched_response_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_socket_path(tmp_path)
    response = DaemonResponse(
        request_id="another-request",
        status="ok",
    ).to_json_line()
    fake_socket = ClientSocket(response)

    def socket_factory(*args: object, **kwargs: object) -> ClientSocket:
        return fake_socket

    monkeypatch.setattr(client.socket, "socket", socket_factory)

    with pytest.raises(DaemonConnectionError) as captured:
        client.request("ping", project_root=tmp_path)

    assert isinstance(captured.value.__cause__, ProtocolError)
    assert "request_id does not match" in str(captured.value)
    assert captured.value.phase == "response_identity"
    assert captured.value.request_id is not None
    assert captured.value.retryable is True
    assert captured.value.request_may_have_completed is True


def test_client_wraps_extra_response_frame_as_connection_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_socket_path(tmp_path)
    first = DaemonResponse(request_id="one", status="ok").to_json_line()
    second = DaemonResponse(request_id="two", status="ok").to_json_line()

    def socket_factory(*args: object, **kwargs: object) -> ClientSocket:
        return ClientSocket(first + second)

    monkeypatch.setattr(client.socket, "socket", socket_factory)

    with pytest.raises(DaemonConnectionError) as captured:
        client.request("ping", project_root=tmp_path)

    assert isinstance(captured.value.__cause__, DaemonExtraFrameData)
    assert captured.value.phase == "response_decode"
    assert captured.value.request_id is not None
    assert captured.value.retryable is True
    assert captured.value.request_may_have_completed is True


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_client_rejects_invalid_timeout(timeout: object) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        client.request("ping", timeout=timeout)  # type: ignore[arg-type]


def test_ping_forwards_readiness_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_timeout = 0.0

    def fake_request(
        request_type: RequestType,
        payload: dict[str, JsonValue] | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        nonlocal captured_timeout
        del payload
        assert request_type == "ping"
        assert project_root == tmp_path
        captured_timeout = timeout
        return DaemonResponse(
            request_id="ping-request",
            status="ok",
            payload=MessagePayload(message="pong").to_wire(),
        )

    monkeypatch.setattr(client, "request", fake_request)

    assert client.ping(tmp_path, timeout=0.125) is True
    assert captured_timeout == 0.125


def test_shutdown_forwards_remaining_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_timeout = 0.0

    def fake_request(
        request_type: RequestType,
        payload: dict[str, JsonValue] | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        nonlocal captured_timeout
        del payload
        assert request_type == "shutdown"
        assert project_root == tmp_path
        captured_timeout = timeout
        return DaemonResponse(
            request_id="shutdown-request",
            status="ok",
            payload=MessagePayload(message="shutdown requested").to_wire(),
        )

    monkeypatch.setattr(client, "request", fake_request)

    client.shutdown(tmp_path, timeout=0.125)
    assert captured_timeout == 0.125


def test_activity_client_rejects_lossy_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(
        request_type: RequestType,
        payload: dict[str, JsonValue] | None = None,
        *,
        project_root: Path | None = None,
        timeout: float = 2.0,
    ) -> DaemonResponse:
        del payload, project_root, timeout
        assert request_type == "activity_next"
        return DaemonResponse(
            request_id="activity-request",
            status="ok",
            payload=ActivityEventsResponsePayload(
                (),
                dropped_count=3,
            ).to_wire(),
        )

    monkeypatch.setattr(client, "request", fake_request)

    with pytest.raises(ActivityStreamGapError) as captured:
        client.next_activity("sub-1", timeout_ms=0)

    assert captured.value.dropped_count == 3


def test_typed_response_decoder_distinguishes_application_failure() -> None:
    with pytest.raises(
        DaemonApplicationError,
        match="request rejected",
    ):
        client.decode_response(
            DaemonResponse.fail("r", "request rejected"),
            MessagePayload.from_wire,
            operation="ping",
        )


def test_typed_response_decoder_wraps_malformed_success() -> None:
    with pytest.raises(DaemonConnectionError) as captured:
        client.decode_response(
            DaemonResponse(
                request_id="r",
                status="ok",
                payload={"unexpected": True},
            ),
            MessagePayload.from_wire,
            operation="ping",
        )

    assert isinstance(captured.value.__cause__, ProtocolError)
    assert "ping response is malformed" in str(captured.value)
    assert captured.value.phase == "payload_decode"
    assert captured.value.request_id == "r"
    assert captured.value.retryable is False
    assert captured.value.request_may_have_completed is True
