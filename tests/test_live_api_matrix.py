from __future__ import annotations

import pytest

from nuself.live_testing import (
    OPENCODE_GO_LIVE_MATRIX,
    LiveModelCase,
    LiveModelSpec,
    parse_live_model_matrix,
    parse_live_model_spec,
    select_live_model_cases,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "openai:glm-5.1",
            LiveModelSpec(provider="openai", model="glm-5.1"),
        ),
        (
            "anthropic:minimax-m2.7",
            LiveModelSpec(
                provider="anthropic",
                model="minimax-m2.7",
            ),
        ),
    ],
)
def test_parse_live_model_spec(
    raw: str,
    expected: LiveModelSpec,
) -> None:
    assert parse_live_model_spec(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "glm-5.1",
        "unknown:glm-5.1",
        "openai:",
        "openai:glm 5.1",
    ],
)
def test_parse_live_model_spec_rejects_invalid_value(raw: str) -> None:
    with pytest.raises(ValueError, match="live model"):
        parse_live_model_spec(raw)


def test_parse_live_model_matrix_preserves_order() -> None:
    result = parse_live_model_matrix(
        [
            "openai:glm-5.1",
            "anthropic:minimax-m2.7",
        ]
    )

    assert [item.id for item in result] == [
        "openai:glm-5.1",
        "anthropic:minimax-m2.7",
    ]


def test_parse_live_model_matrix_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        parse_live_model_matrix(
            [
                "openai:glm-5.1",
                "openai:glm-5.1",
            ]
        )


def test_select_live_model_cases_uses_explicit_models() -> None:
    result = select_live_model_cases(
        ["openai:glm-5.1"],
        opencode_go_matrix=False,
    )

    assert result == (
        LiveModelCase(
            LiveModelSpec(provider="openai", model="glm-5.1")
        ),
    )


def test_select_live_model_cases_uses_curated_go_matrix() -> None:
    result = select_live_model_cases(
        [],
        opencode_go_matrix=True,
    )

    assert result == OPENCODE_GO_LIVE_MATRIX
    assert len({case.spec.id for case in result}) == len(result)
    assert {
        case.spec.provider for case in result
    } == {"openai", "anthropic"}


def test_select_live_model_cases_rejects_conflicting_modes() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        select_live_model_cases(
            ["openai:glm-5.1"],
            opencode_go_matrix=True,
        )


def test_live_model_case_rejects_conflicting_capability_state() -> None:
    with pytest.raises(ValueError, match="both unsupported and unstable"):
        LiveModelCase(
            LiveModelSpec(provider="openai", model="example"),
            unsupported=frozenset({"tool"}),
            unstable=frozenset({"tool"}),
        )
