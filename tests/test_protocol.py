from __future__ import annotations

from nuself.daemon.protocol import DaemonRequest, DaemonResponse, ProtocolError


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
