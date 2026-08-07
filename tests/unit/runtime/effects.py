from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from nuself.runtime.feature.codec import (
    ToolEffectCodec,
    decode_effect_request,
    decode_effect_resolution,
    encode_effect_request,
    encode_effect_resolution,
)
from nuself.runtime.feature.protocol import (
    ToolEffectRequest,
    ToolEffectResolution,
)


@dataclass(frozen=True)
class ChoiceRequest(ToolEffectRequest):
    choices: tuple[str, ...]

    @property
    def kind(self) -> str:
        return "test.choice"


@dataclass(frozen=True)
class ChoiceResolution(ToolEffectResolution):
    selected: str

    @property
    def kind(self) -> str:
        return "test.choice"


class ChoiceCodec:
    kind = "test.choice"
    request_type = ChoiceRequest
    resolution_type = ChoiceResolution

    def encode_request(
        self,
        request: ToolEffectRequest,
    ) -> dict[str, object]:
        assert isinstance(request, ChoiceRequest)
        return {
            "kind": self.kind,
            "component": request.component,
            "operation": request.operation,
            "choices": list(request.choices),
        }

    def decode_request(
        self,
        payload: Mapping[str, object],
    ) -> ToolEffectRequest:
        choices = payload["choices"]
        assert isinstance(choices, list)
        untyped_choices = cast(list[object], choices)
        assert all(isinstance(choice, str) for choice in untyped_choices)
        return ChoiceRequest(
            component=str(payload["component"]),
            operation=str(payload["operation"]),
            choices=tuple(
                choice
                for choice in untyped_choices
                if isinstance(choice, str)
            ),
        )

    def encode_resolution(
        self,
        resolution: ToolEffectResolution,
    ) -> dict[str, object]:
        assert isinstance(resolution, ChoiceResolution)
        return {
            "kind": self.kind,
            "request": self.encode_request(resolution.request),
            "selected": resolution.selected,
        }

    def decode_resolution(
        self,
        payload: Mapping[str, object],
    ) -> ToolEffectResolution:
        request_payload = payload["request"]
        assert isinstance(request_payload, Mapping)
        request = self.decode_request(
            cast(Mapping[str, object], request_payload)
        )
        selected = payload["selected"]
        assert isinstance(selected, str)
        return ChoiceResolution(request, selected)


def test_non_approval_effect_family_round_trips_through_generic_codec() -> None:
    codecs: tuple[ToolEffectCodec, ...] = (ChoiceCodec(),)
    request = ChoiceRequest(
        component="test",
        operation="choose_target",
        choices=("first", "second"),
    )
    resolution = ChoiceResolution(request, "second")

    encoded_request = encode_effect_request(request, codecs=codecs)
    encoded_resolution = encode_effect_resolution(
        resolution,
        codecs=codecs,
    )

    assert decode_effect_request(encoded_request, codecs=codecs) == request
    assert decode_effect_resolution(
        encoded_resolution,
        codecs=codecs,
    ) == resolution
