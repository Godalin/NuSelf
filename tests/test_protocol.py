from __future__ import annotations

import pytest

from nuself.daemon.protocol import (
    MAX_DAEMON_FRAME_BYTES,
    DaemonFrameTooLarge,
    DaemonIncompleteFrame,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
)


def test_request_round_trip() -> None:
    request = DaemonRequest(type="echo", payload={"message": "hello"}, request_id="r1")

    parsed = DaemonRequest.from_json_line(request.to_json_line())

    assert parsed == request


def test_response_round_trip() -> None:
    request = DaemonRequest(type="ping", request_id="r2")
    response = DaemonResponse.ok(request, {"message": "pong"})

    parsed = DaemonResponse.from_json_line(response.to_json_line())

    assert parsed == response


def test_request_rejects_unknown_type() -> None:
    line = b'{"version":1,"request_id":"r3","type":"old_ping","payload":{}}\n'

    try:
        DaemonRequest.from_json_line(line)
    except ProtocolError:
        return
    raise AssertionError("expected ProtocolError")


def test_request_rejects_malformed_json() -> None:
    line = b"not json at all\n"

    try:
        DaemonRequest.from_json_line(line)
    except ProtocolError as exc:
        assert "invalid json" in str(exc)
        return
    raise AssertionError("expected ProtocolError")


def test_protocol_rejects_missing_newline_and_invalid_utf8() -> None:
    with pytest.raises(DaemonIncompleteFrame):
        DaemonRequest.from_json_line(
            b'{"version":1,"request_id":"r","type":"ping","payload":{}}'
        )
    with pytest.raises(ProtocolError, match="UTF-8"):
        DaemonRequest.from_json_line(b"\xff\n")


def test_protocol_rejects_non_finite_json_numbers() -> None:
    with pytest.raises(ProtocolError, match="invalid JSON constant"):
        DaemonRequest.from_json_line(
            b'{"version":1,"request_id":"r","type":"echo",'
            b'"payload":{"value":NaN}}\n'
        )
    with pytest.raises(ProtocolError, match="non-finite number"):
        DaemonRequest(
            type="echo",
            payload={"value": float("inf")},
        ).to_json_line()


@pytest.mark.parametrize(
    "line, error",
    [
        (
            b'{"version":true,"request_id":"r","type":"ping",'
            b'"payload":{}}\n',
            "version",
        ),
        (
            b'{"version":1,"request_id":"","type":"ping",'
            b'"payload":{}}\n',
            "non-empty",
        ),
        (
            b'{"version":1,"request_id":"   ","type":"ping",'
            b'"payload":{}}\n',
            "non-empty",
        ),
        (
            b'{"version":1,"request_id":"r","type":"ping",'
            b'"payload":{},"extra":true}\n',
            "unknown envelope field",
        ),
        (
            b'{"version":1,"request_id":"first",'
            b'"request_id":"second","type":"ping","payload":{}}\n',
            "duplicate JSON object field",
        ),
        (
            b'{"version":1,"request_id":"r","type":"echo",'
            b'"payload":{"value":1e999}}\n',
            "non-finite number",
        ),
        (
            b'{"version":1,"request_id":"r","type":"echo",'
            b'"payload":{"value":1,"value":2}}\n',
            "duplicate JSON object field",
        ),
    ],
)
def test_request_rejects_ambiguous_envelope_fields(
    line: bytes,
    error: str,
) -> None:
    with pytest.raises(ProtocolError, match=error):
        DaemonRequest.from_json_line(line)


@pytest.mark.parametrize(
    "daemon_request",
    [
        DaemonRequest(
            type="ping",
            request_id="",
        ),
        DaemonRequest(
            type="ping",
            version=True,  # type: ignore[arg-type]
        ),
        DaemonRequest(
            type="echo",
            payload={1: "not a string key"},  # type: ignore[dict-item]
        ),
        DaemonRequest(
            type="echo",
            payload={"nested": [object()]},  # type: ignore[list-item]
        ),
    ],
)
def test_request_encode_enforces_wire_contract(
    daemon_request: DaemonRequest,
) -> None:
    with pytest.raises(ProtocolError):
        daemon_request.to_json_line()


def test_protocol_rejects_oversized_frame() -> None:
    with pytest.raises(DaemonFrameTooLarge):
        DaemonRequest.from_json_line(
            b"x" * MAX_DAEMON_FRAME_BYTES + b"\n"
        )


def test_request_rejects_version_mismatch() -> None:
    line = b'{"version":99,"request_id":"r4","type":"ping","payload":{}}\n'

    try:
        DaemonRequest.from_json_line(line)
    except ProtocolError as exc:
        assert "unsupported protocol version" in str(exc)
        return
    raise AssertionError("expected ProtocolError")


def test_request_rejects_missing_required_field() -> None:
    line = b'{"version":1,"type":"ping","payload":{}}\n'

    try:
        DaemonRequest.from_json_line(line)
    except ProtocolError as exc:
        assert "request_id" in str(exc)
        return
    raise AssertionError("expected ProtocolError")


def test_response_rejects_invalid_status() -> None:
    line = b'{"version":1,"request_id":"r5","status":"maybe","payload":{}}\n'

    try:
        DaemonResponse.from_json_line(line)
    except ProtocolError as exc:
        assert "unsupported response status" in str(exc)
        return
    raise AssertionError("expected ProtocolError")


def test_health_request_round_trips() -> None:
    request = DaemonRequest(
        type="health", payload={}, request_id="health-request"
    )
    decoded = DaemonRequest.from_json_line(request.to_json_line())
    assert decoded.type == "health"


def test_response_rejects_non_string_error() -> None:
    line = b'{"version":1,"request_id":"r6","status":"error","payload":{},"error":123}\n'

    try:
        DaemonResponse.from_json_line(line)
    except ProtocolError as exc:
        assert "error" in str(exc)
        return
    raise AssertionError("expected ProtocolError")


def test_response_parses_error_field() -> None:
    line = b'{"version":1,"request_id":"r7","status":"error","payload":{},"error":"something failed"}\n'

    response = DaemonResponse.from_json_line(line)

    assert response.status == "error"
    assert response.error == "something failed"


@pytest.mark.parametrize(
    "line, error",
    [
        (
            b'{"version":1,"request_id":"r","status":"ok",'
            b'"payload":{},"error":"unexpected"}\n',
            "absent",
        ),
        (
            b'{"version":1,"request_id":"r","status":"error",'
            b'"payload":{}}\n',
            "error",
        ),
        (
            b'{"version":1,"request_id":"r","status":"error",'
            b'"payload":{},"error":""}\n',
            "non-empty",
        ),
        (
            b'{"version":1,"request_id":"r","status":"ok",'
            b'"payload":{},"extra":null}\n',
            "unknown envelope field",
        ),
    ],
)
def test_response_enforces_status_error_contract(
    line: bytes,
    error: str,
) -> None:
    with pytest.raises(ProtocolError, match=error):
        DaemonResponse.from_json_line(line)


@pytest.mark.parametrize(
    "response",
    [
        DaemonResponse(
            request_id="r",
            status="ok",
            error="unexpected",
        ),
        DaemonResponse(
            request_id="r",
            status="error",
        ),
        DaemonResponse(
            request_id="r",
            status="error",
            error="",
        ),
    ],
)
def test_response_encode_enforces_status_error_contract(
    response: DaemonResponse,
) -> None:
    with pytest.raises(ProtocolError):
        response.to_json_line()


def test_failed_response_factory_backstops_blank_diagnostic() -> None:
    response = DaemonResponse.fail("r", "   ")

    assert response.error == "daemon request failed"
    assert DaemonResponse.from_json_line(
        response.to_json_line()
    ) == response


def test_failed_response_exception_factory_is_safe_and_sanitized() -> None:
    class BrokenMessageError(RuntimeError):
        def __str__(self) -> str:
            raise KeyboardInterrupt

    assert (
        DaemonResponse.fail_from_exception(
            "broken",
            BrokenMessageError(),
        ).error
        == "BrokenMessageError"
    )
    assert (
        DaemonResponse.fail_from_exception(
            "secret",
            RuntimeError("failed api_key=private-value"),
        ).error
        == "failed api_key=***"
    )


def test_failed_response_exception_factory_sanitizes_compact_chain() -> None:
    root = ValueError("provider password=root-secret")
    outer = RuntimeError("request failed token=outer-secret")
    outer.__cause__ = root

    response = DaemonResponse.fail_from_exception(
        "chain",
        outer,
        include_chain=True,
    )

    assert response.error == (
        "request failed token=*** <- provider password=***"
    )
    assert "root-secret" not in response.to_json_line().decode()
    assert "outer-secret" not in response.to_json_line().decode()
