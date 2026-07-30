"""Typed terminal control decisions shared by one-shot CLI prompts."""

from __future__ import annotations

from enum import Enum


class ConfirmationDecision(str, Enum):
    YES = "yes"
    NO = "no"
    INTERRUPTED = "interrupted"


def read_confirmation(prompt: str) -> ConfirmationDecision:
    """Read one safe-default confirmation without leaking terminal control."""

    try:
        answer = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return ConfirmationDecision.INTERRUPTED
    if answer.strip().casefold() in {"y", "yes"}:
        return ConfirmationDecision.YES
    return ConfirmationDecision.NO
