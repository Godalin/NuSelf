"""JSONL protocol used between the CLI and the local daemon."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Literal, cast
from uuid import uuid4

from nuself.runtime.diagnostics import (
    diagnostic_exception_chain,
    diagnostic_exception_message,
)

PROTOCOL_VERSION = 1
MAX_DAEMON_FRAME_BYTES = 1024 * 1024

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
type RequestType = Literal[
    "ping",
    "health",
    "chat",
    "shutdown",
    "activity_open",
    "activity_next",
    "activity_close",
]
type ResponseStatus = Literal["ok", "error"]
REQUEST_TYPES: tuple[RequestType, ...] = (
    "ping",
    "health",
    "chat",
    "shutdown",
    "activity_open",
    "activity_next",
    "activity_close",
)
_REQUEST_FIELDS = frozenset(
    {"version", "request_id", "type", "payload"}
)
_RESPONSE_REQUIRED_FIELDS = frozenset(
    {"version", "request_id", "status", "payload"}
)
_RESPONSE_OPTIONAL_FIELDS = frozenset({"error"})


class ProtocolError(ValueError):
    """Raised when a protocol payload is malformed."""


class DaemonPeerDisconnected(ProtocolError):
    """Raised when a peer closes before sending any frame bytes."""


class DaemonFrameTooLarge(ProtocolError):
    """Raised when one JSONL frame exceeds the shared byte limit."""


class DaemonIncompleteFrame(ProtocolError):
    """Raised when EOF arrives before a terminating newline."""


class DaemonExtraFrameData(ProtocolError):
    """Raised when a one-frame connection sends bytes after its newline."""


@dataclass(frozen=True)
class DaemonRequest:
    """Request sent from a CLI client to the daemon."""

    type: RequestType
    payload: dict[str, JsonValue] = field(
        default_factory=dict[str, JsonValue]
    )
    request_id: str = field(default_factory=lambda: uuid4().hex)
    version: int = PROTOCOL_VERSION

    def to_json_line(self) -> bytes:
        wire = self.to_wire()
        _validate_request_wire(wire)
        return _encode_json_line(wire)

    def to_wire(self) -> dict[str, JsonValue]:
        return {
            "version": self.version,
            "request_id": self.request_id,
            "type": self.type,
            "payload": self.payload,
        }

    @classmethod
    def from_json_line(cls, line: bytes) -> DaemonRequest:
        raw = _decode_json_object(line)
        version, request_id, request_type, payload = (
            _validate_request_wire(raw)
        )
        return cls(
            type=request_type, payload=payload, request_id=request_id, version=version
        )


@dataclass(frozen=True)
class DaemonResponse:
    """Response sent from the daemon to a CLI client."""

    request_id: str
    status: ResponseStatus
    payload: dict[str, JsonValue] = field(
        default_factory=dict[str, JsonValue]
    )
    error: str | None = None
    version: int = PROTOCOL_VERSION

    def to_json_line(self) -> bytes:
        wire = self.to_wire()
        _validate_response_wire(wire)
        return _encode_json_line(wire)

    def to_wire(self) -> dict[str, JsonValue]:
        wire: dict[str, JsonValue] = {
            "version": self.version,
            "request_id": self.request_id,
            "status": self.status,
            "payload": self.payload,
        }
        if self.error is not None:
            wire["error"] = self.error
        return wire

    @classmethod
    def ok(
        cls, request: DaemonRequest, payload: dict[str, JsonValue] | None = None
    ) -> DaemonResponse:
        return cls(request_id=request.request_id, status="ok", payload=payload or {})

    @classmethod
    def fail(cls, request_id: str, error: str) -> DaemonResponse:
        detail = error.strip() or "daemon request failed"
        return cls(
            request_id=request_id,
            status="error",
            error=detail,
        )

    @classmethod
    def fail_from_exception(
        cls,
        request_id: str,
        error: BaseException,
        *,
        include_chain: bool = False,
    ) -> DaemonResponse:
        """Build a failed response from safe diagnostic exception text."""

        detail = (
            diagnostic_exception_chain(error)
            if include_chain
            else diagnostic_exception_message(error)
        )
        return cls.fail(request_id, detail)

    @classmethod
    def from_json_line(cls, line: bytes) -> DaemonResponse:
        raw = _decode_json_object(line)
        version, request_id, status, payload, error_value = (
            _validate_response_wire(raw)
        )
        return cls(
            request_id=request_id,
            status=status,
            payload=payload,
            error=error_value,
            version=version,
        )


def _decode_json_object(line: bytes) -> dict[str, Any]:
    _validate_json_line_frame(line)
    try:
        value = json.loads(
            line.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_decode_object_pairs,
        )
    except UnicodeDecodeError as exc:
        raise ProtocolError("frame is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolError(
            f"invalid json: {diagnostic_exception_message(exc)}"
        ) from exc
    except ProtocolError:
        raise
    except ValueError as exc:
        raise ProtocolError(diagnostic_exception_message(exc)) from exc
    if not isinstance(value, dict):
        raise ProtocolError("payload must be a JSON object")
    _validate_json_value(cast(object, value), path="$")
    return cast(dict[str, Any], value)


def _encode_json_line(wire: dict[str, JsonValue]) -> bytes:
    try:
        frame = (
            json.dumps(
                wire,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("daemon frame is not valid JSON") from exc
    if len(frame) > MAX_DAEMON_FRAME_BYTES:
        raise DaemonFrameTooLarge(
            f"daemon frame exceeds {MAX_DAEMON_FRAME_BYTES} bytes"
        )
    return frame


def _validate_json_line_frame(line: bytes) -> None:
    if not line:
        raise DaemonPeerDisconnected(
            "peer closed connection before sending a frame"
        )
    if len(line) > MAX_DAEMON_FRAME_BYTES:
        raise DaemonFrameTooLarge(
            f"daemon frame exceeds {MAX_DAEMON_FRAME_BYTES} bytes"
        )
    if not line.endswith(b"\n"):
        raise DaemonIncompleteFrame(
            "daemon frame ended before its newline"
        )
    if b"\n" in line[:-1]:
        raise DaemonExtraFrameData(
            "daemon connection contains more than one frame"
        )


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


def _decode_object_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ProtocolError(f"duplicate JSON object field: {key}")
        value[key] = item
    return value


def _validate_request_wire(
    raw: dict[str, Any],
) -> tuple[int, str, RequestType, dict[str, JsonValue]]:
    _expect_fields(raw, required=_REQUEST_FIELDS)
    version = _expect_protocol_version(raw)
    request_id = _expect_non_empty_str(raw, "request_id")
    request_type = _expect_request_type(raw, "type")
    payload = _expect_object(raw, "payload")
    _validate_json_value(payload, path="payload")
    return version, request_id, request_type, payload


def _validate_response_wire(
    raw: dict[str, Any],
) -> tuple[
    int,
    str,
    ResponseStatus,
    dict[str, JsonValue],
    str | None,
]:
    _expect_fields(
        raw,
        required=_RESPONSE_REQUIRED_FIELDS,
        optional=_RESPONSE_OPTIONAL_FIELDS,
    )
    version = _expect_protocol_version(raw)
    request_id = _expect_non_empty_str(raw, "request_id")
    status = _expect_response_status(raw, "status")
    payload = _expect_object(raw, "payload")
    _validate_json_value(payload, path="payload")
    if status == "ok":
        if "error" in raw:
            raise ProtocolError(
                "field 'error' must be absent for an ok response"
            )
        error_value = None
    else:
        error_value = _expect_non_empty_str(raw, "error")
    return version, request_id, status, payload, error_value


def _expect_fields(
    raw: dict[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    unknown = raw.keys() - required - optional
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ProtocolError(f"unknown envelope field(s): {names}")


def _expect_protocol_version(raw: dict[str, Any]) -> int:
    version = _expect_int(raw, "version")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {version}")
    return version


def _validate_json_value(value: object, *, path: str) -> JsonValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ProtocolError(
                f"field '{path}' contains a non-finite number"
            )
        return value
    if isinstance(value, list):
        sequence = cast(list[object], value)
        return [
            _validate_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(sequence)
        ]
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        result: dict[str, JsonValue] = {}
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise ProtocolError(
                    f"field '{path}' contains a non-string object key"
                )
            result[key] = _validate_json_value(
                item,
                path=f"{path}.{key}",
            )
        return result
    raise ProtocolError(
        f"field '{path}' contains non-JSON value "
        f"{type(value).__name__}"
    )


def _expect_object(raw: dict[str, Any], field_name: str) -> dict[str, JsonValue]:
    value = raw.get(field_name)
    if not isinstance(value, dict):
        raise ProtocolError(f"field '{field_name}' must be an object")
    return cast(dict[str, JsonValue], value)


def _expect_str(raw: dict[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str):
        raise ProtocolError(f"field '{field_name}' must be a string")
    return value


def _expect_non_empty_str(
    raw: dict[str, Any],
    field_name: str,
) -> str:
    value = _expect_str(raw, field_name)
    if not value.strip():
        raise ProtocolError(
            f"field '{field_name}' must be a non-empty string"
        )
    return value


def _expect_int(raw: dict[str, Any], field_name: str) -> int:
    value = raw.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"field '{field_name}' must be an integer")
    return value


def _expect_request_type(raw: dict[str, Any], field_name: str) -> RequestType:
    value = _expect_str(raw, field_name)
    if value not in REQUEST_TYPES:
        raise ProtocolError(f"unsupported request type: {value}")
    return value


def _expect_response_status(raw: dict[str, Any], field_name: str) -> ResponseStatus:
    value = _expect_str(raw, field_name)
    if value not in {"ok", "error"}:
        raise ProtocolError(f"unsupported response status: {value}")
    return cast(ResponseStatus, value)
