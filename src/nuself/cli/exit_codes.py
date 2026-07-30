"""Typed process exit statuses owned by the NuSelf CLI."""

from __future__ import annotations

from enum import IntEnum


class CliExitCode(IntEnum):
    """Stable CLI outcomes; integers are exposed only at the process boundary."""

    SUCCESS = 0
    FAILURE = 1
    USAGE = 2
    SETUP_REQUIRED = 3
    TEMPORARY_FAILURE = 4
    CORRUPT_STATE = 5
    INTERRUPTED = 130
