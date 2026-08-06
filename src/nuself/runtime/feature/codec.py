"""Closed, injectable wire codecs for suspending Tool effects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Protocol, cast

from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.feature.approval import (
    ApprovalEffectDecision,
    ApprovalEffectRequest,
    ApprovalEffectResolution,
)
from nuself.runtime.feature.protocol import (
    ToolEffectRequest,
    ToolEffectResolution,
)


class ToolEffectCodecError(ValueError):
    """A Tool effect wire value is malformed or unsupported."""


class ToolEffectCodec(Protocol):
    """Closed codec capability for one request/resolution family."""

    kind: str
    @property
    def request_type(self) -> type[ToolEffectRequest]: ...

    @property
    def resolution_type(self) -> type[ToolEffectResolution]: ...

    def encode_request(
        self,
        request: ToolEffectRequest,
    ) -> dict[str, object]: ...

    def decode_request(
        self,
        payload: Mapping[str, object],
    ) -> ToolEffectRequest: ...

    def encode_resolution(
        self,
        resolution: ToolEffectResolution,
    ) -> dict[str, object]: ...

    def decode_resolution(
        self,
        payload: Mapping[str, object],
    ) -> ToolEffectResolution: ...


class ApprovalToolEffectCodec:
    """Wire codec for the approval interaction family."""

    kind = "approval"
    request_type = ApprovalEffectRequest
    resolution_type = ApprovalEffectResolution

    def encode_request(
        self,
        request: ToolEffectRequest,
    ) -> dict[str, object]:
        if not isinstance(request, ApprovalEffectRequest):
            raise ToolEffectCodecError("approval request type is invalid")
        return {
            "kind": self.kind,
            "component": request.component,
            "operation": request.operation,
            "action": request.action,
            "resource": request.resource,
            "risk": request.risk,
            "summary": request.summary,
        }

    def decode_request(
        self,
        payload: Mapping[str, object],
    ) -> ToolEffectRequest:
        _fields(payload, {
            "kind",
            "component",
            "operation",
            "action",
            "resource",
            "risk",
            "summary",
        })
        risk = _string(payload, "risk", "approval request")
        if risk not in {"reversible", "destructive", "external"}:
            raise ToolEffectCodecError("approval request risk is invalid")
        return ApprovalEffectRequest(
            component=_string(payload, "component", "approval request"),
            operation=_string(payload, "operation", "approval request"),
            action=_string(payload, "action", "approval request"),
            resource=_string(payload, "resource", "approval request"),
            risk=cast(
                Literal["reversible", "destructive", "external"],
                risk,
            ),
            summary=_string(payload, "summary", "approval request"),
        )

    def encode_resolution(
        self,
        resolution: ToolEffectResolution,
    ) -> dict[str, object]:
        if not isinstance(resolution, ApprovalEffectResolution):
            raise ToolEffectCodecError("approval resolution type is invalid")
        return {
            "kind": self.kind,
            "request": self.encode_request(resolution.request),
            "decision": {
                "approved": resolution.decision.approved,
                "approver": resolution.decision.approver,
                "input_kind": resolution.decision.input_kind,
            },
        }

    def decode_resolution(
        self,
        payload: Mapping[str, object],
    ) -> ToolEffectResolution:
        _fields(payload, {"kind", "request", "decision"})
        request = self.decode_request(
            _mapping(payload["request"], "approval request")
        )
        assert isinstance(request, ApprovalEffectRequest)
        decision = _mapping(payload["decision"], "approval decision")
        _fields(decision, {"approved", "approver", "input_kind"})
        approved = decision["approved"]
        if not isinstance(approved, bool):
            raise ToolEffectCodecError(
                "approval decision approved must be a boolean"
            )
        approver = decision["approver"]
        if approver is not None and not isinstance(approver, str):
            raise ToolEffectCodecError(
                "approval decision approver must be a string or null"
            )
        input_kind = _string(decision, "input_kind", "approval decision")
        if input_kind not in {
            "affirmative",
            "declined",
            "eof",
            "interrupt",
            "unavailable",
        }:
            raise ToolEffectCodecError(
                "approval decision input_kind is invalid"
            )
        try:
            approval = ApprovalEffectDecision(
                approved=approved,
                approver=approver,
                input_kind=cast(
                    Literal[
                        "affirmative",
                        "declined",
                        "eof",
                        "interrupt",
                        "unavailable",
                    ],
                    input_kind,
                ),
            )
        except ValueError as exc:
            raise ToolEffectCodecError(
                diagnostic_exception_message(exc)
            ) from exc
        return ApprovalEffectResolution(request, approval)


DEFAULT_TOOL_EFFECT_CODECS: tuple[ToolEffectCodec, ...] = (
    ApprovalToolEffectCodec(),
)


def encode_effect_request(
    request: ToolEffectRequest,
    *,
    codecs: tuple[ToolEffectCodec, ...] = DEFAULT_TOOL_EFFECT_CODECS,
) -> dict[str, object]:
    """Encode a request through its exact typed codec."""

    codec = _codec_for_type(request, codecs, resolution=False)
    return codec.encode_request(request)


def decode_effect_request(
    value: object,
    *,
    codecs: tuple[ToolEffectCodec, ...] = DEFAULT_TOOL_EFFECT_CODECS,
) -> ToolEffectRequest:
    """Decode a request through its discriminated typed codec."""

    payload = _mapping(value, "Tool effect request")
    codec = _codec_for_kind(payload, codecs)
    return codec.decode_request(payload)


def encode_effect_resolution(
    resolution: ToolEffectResolution,
    *,
    codecs: tuple[ToolEffectCodec, ...] = DEFAULT_TOOL_EFFECT_CODECS,
) -> dict[str, object]:
    """Encode a resolution through its exact typed codec."""

    codec = _codec_for_type(resolution, codecs, resolution=True)
    return codec.encode_resolution(resolution)


def decode_effect_resolution(
    value: object,
    *,
    codecs: tuple[ToolEffectCodec, ...] = DEFAULT_TOOL_EFFECT_CODECS,
) -> ToolEffectResolution:
    """Decode a resolution through its discriminated typed codec."""

    payload = _mapping(value, "Tool effect resolution")
    codec = _codec_for_kind(payload, codecs)
    return codec.decode_resolution(payload)


def _codec_for_type(
    value: ToolEffectRequest | ToolEffectResolution,
    codecs: tuple[ToolEffectCodec, ...],
    *,
    resolution: bool,
) -> ToolEffectCodec:
    for codec in codecs:
        expected = codec.resolution_type if resolution else codec.request_type
        if isinstance(value, expected):
            return codec
    raise ToolEffectCodecError(
        f"unsupported Tool effect type: {type(value).__name__}"
    )


def _codec_for_kind(
    payload: Mapping[str, object],
    codecs: tuple[ToolEffectCodec, ...],
) -> ToolEffectCodec:
    kind = _string(payload, "kind", "Tool effect")
    matches = tuple(codec for codec in codecs if codec.kind == kind)
    if len(matches) != 1:
        raise ToolEffectCodecError(
            f"unsupported or ambiguous Tool effect kind: {kind!r}"
        )
    return matches[0]


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ToolEffectCodecError(f"{context} must be an object")
    untyped = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in untyped):
        raise ToolEffectCodecError(f"{context} must be an object")
    return cast(Mapping[str, object], value)


def _fields(payload: Mapping[str, object], required: set[str]) -> None:
    actual = set(payload)
    if actual != required:
        raise ToolEffectCodecError(
            "Tool effect fields are invalid: "
            f"expected {sorted(required)!r}, got {sorted(actual)!r}"
        )


def _string(
    payload: Mapping[str, object],
    field: str,
    context: str,
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ToolEffectCodecError(
            f"{context} field {field!r} must be a non-blank string"
        )
    return value
