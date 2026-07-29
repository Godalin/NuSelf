"""Validated selections shared by opt-in live-provider tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

LiveProvider = Literal["openai", "anthropic"]
LiveCapability = Literal[
    "transport",
    "structured",
    "chat",
    "tool",
]


@dataclass(frozen=True)
class LiveModelSpec:
    """One explicit provider/model pair selected by a live-test caller."""

    provider: LiveProvider
    model: str

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class LiveModelCase:
    """One model plus observed capability gaps enforced by strict xfail."""

    spec: LiveModelSpec
    unsupported: frozenset[LiveCapability] = frozenset()
    unstable: frozenset[LiveCapability] = frozenset()

    def __post_init__(self) -> None:
        if self.unsupported & self.unstable:
            raise ValueError(
                "live capability cannot be both unsupported and unstable"
            )


OPENCODE_GO_LIVE_MATRIX: tuple[LiveModelCase, ...] = (
    LiveModelCase(
        LiveModelSpec(provider="openai", model="glm-5.1"),
    ),
    LiveModelCase(
        LiveModelSpec(provider="openai", model="kimi-k2.6"),
        unstable=frozenset({"tool"}),
    ),
    LiveModelCase(
        LiveModelSpec(
            provider="openai",
            model="deepseek-v4-flash",
        ),
        unsupported=frozenset({"structured", "chat", "tool"}),
    ),
    LiveModelCase(
        LiveModelSpec(
            provider="anthropic",
            model="minimax-m2.7",
        ),
    ),
    LiveModelCase(
        LiveModelSpec(
            provider="anthropic",
            model="qwen3.7-plus",
        ),
    ),
)


def parse_live_model_spec(raw: str) -> LiveModelSpec:
    """Parse one exact ``provider:model`` selection without inference."""

    provider_raw, separator, model_raw = raw.partition(":")
    provider = provider_raw.strip()
    model = model_raw.strip()
    if separator == "" or provider not in {"openai", "anthropic"} or not model:
        raise ValueError(
            "live model must use provider:model with provider "
            "'openai' or 'anthropic'"
        )
    if any(character.isspace() for character in model):
        raise ValueError("live model id must not contain whitespace")
    return LiveModelSpec(
        provider=cast(LiveProvider, provider),
        model=model,
    )


def parse_live_model_matrix(
    values: list[str],
) -> tuple[LiveModelSpec, ...]:
    """Parse a unique ordered matrix before any provider request."""

    result = tuple(parse_live_model_spec(value) for value in values)
    identities = [item.id for item in result]
    if len(set(identities)) != len(identities):
        raise ValueError("live model matrix must not contain duplicates")
    return result


def select_live_model_cases(
    values: list[str],
    *,
    opencode_go_matrix: bool,
) -> tuple[LiveModelCase, ...]:
    """Select either explicit all-capability models or the curated Go matrix."""

    if values and opencode_go_matrix:
        raise ValueError(
            "--live-model and --live-opencode-go-matrix are mutually exclusive"
        )
    if opencode_go_matrix:
        return OPENCODE_GO_LIVE_MATRIX
    return tuple(
        LiveModelCase(spec)
        for spec in parse_live_model_matrix(values)
    )
