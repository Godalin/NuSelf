"""JSONL protocol used between the CLI and the local daemon."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Literal, TypeAlias, cast
from uuid import uuid4

PROTOCOL_VERSION = 1

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
RequestType: TypeAlias = Literal["ping", "echo", "chat", "shutdown"]
ResponseStatus: TypeAlias = Literal["ok", "error"]


class ProtocolError(ValueError):
    """Raised when a protocol payload is malformed."""


def empty_payload() -> dict[str, JsonValue]:
    return {}


def new_request_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class DaemonRequest:
    """Request sent from a CLI client to the daemon."""

    type: RequestType
    payload: dict[str, JsonValue] = field(default_factory=empty_payload)
    request_id: str = field(default_factory=new_request_id)
    version: int = PROTOCOL_VERSION

    def to_json_line(self) -> bytes:
        return (json.dumps(self.to_wire(), separators=(",", ":")) + "\n").encode("utf-8")

    def to_wire(self) -> dict[str, JsonValue]:
        return {
            "version": self.version,
            "request_id": self.request_id,
            "type": self.type,
            "payload": self.payload,
        }

    @classmethod
    def from_json_line(cls, line: bytes) -> "DaemonRequest":
        raw = _decode_json_object(line)
        version = _expect_int(raw, "version")
        if version != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol version: {version}")
        request_type = _expect_request_type(raw, "type")
        payload = _expect_object(raw, "payload")
        request_id = _expect_str(raw, "request_id")
        return cls(type=request_type, payload=payload, request_id=request_id, version=version)


@dataclass(frozen=True)
class DaemonResponse:
    """Response sent from the daemon to a CLI client."""

    request_id: str
    status: ResponseStatus
    payload: dict[str, JsonValue] = field(default_factory=empty_payload)
    error: str | None = None
    version: int = PROTOCOL_VERSION

    def to_json_line(self) -> bytes:
        return (json.dumps(self.to_wire(), separators=(",", ":")) + "\n").encode("utf-8")

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
    def ok(cls, request: DaemonRequest, payload: dict[str, JsonValue] | None = None) -> "DaemonResponse":
        return cls(request_id=request.request_id, status="ok", payload=payload or {})

    @classmethod
    def fail(cls, request_id: str, error: str) -> "DaemonResponse":
        return cls(request_id=request_id, status="error", error=error)

    @classmethod
    def from_json_line(cls, line: bytes) -> "DaemonResponse":
        raw = _decode_json_object(line)
        version = _expect_int(raw, "version")
        if version != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol version: {version}")
        request_id = _expect_str(raw, "request_id")
        status = _expect_response_status(raw, "status")
        payload = _expect_object(raw, "payload")
        error_value = raw.get("error")
        if error_value is not None and not isinstance(error_value, str):
            raise ProtocolError("field 'error' must be a string")
        return cls(
            request_id=request_id,
            status=status,
            payload=payload,
            error=error_value,
            version=version,
        )


def _decode_json_object(line: bytes) -> dict[str, Any]:
    try:
        value = json.loads(line.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid json: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ProtocolError("payload must be a JSON object")
    return cast(dict[str, Any], value)


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


def _expect_int(raw: dict[str, Any], field_name: str) -> int:
    value = raw.get(field_name)
    if not isinstance(value, int):
        raise ProtocolError(f"field '{field_name}' must be an integer")
    return value


def _expect_request_type(raw: dict[str, Any], field_name: str) -> RequestType:
    value = _expect_str(raw, field_name)
    if value not in {"ping", "echo", "chat", "shutdown"}:
        raise ProtocolError(f"unsupported request type: {value}")
    return cast(RequestType, value)


def _expect_response_status(raw: dict[str, Any], field_name: str) -> ResponseStatus:
    value = _expect_str(raw, field_name)
    if value not in {"ok", "error"}:
        raise ProtocolError(f"unsupported response status: {value}")
    return cast(ResponseStatus, value)
