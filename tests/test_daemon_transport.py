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
from nuself.daemon.payloads import MessagePayload
from nuself.daemon.protocol import (
    MAX_DAEMON_FRAME_BYTES,
    DaemonExtraFrameData,
    DaemonFrameTooLarge,
    DaemonIncompleteFrame,
    DaemonPeerDisconnected,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
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

    with pytest.warns(
        RuntimeWarning,
        match="daemon/response_encode_failed",
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


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_client_rejects_invalid_timeout(timeout: object) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        client.request("ping", timeout=timeout)  # type: ignore[arg-type]


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
