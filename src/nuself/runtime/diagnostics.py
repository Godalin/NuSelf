"""Terminal diagnostics that must never replace a primary outcome."""

from __future__ import annotations

import warnings


def safe_exception_message(
    exc: BaseException,
    *,
    empty: str | None = None,
) -> str:
    """Return exception text without allowing a broken renderer to escape."""

    fallback = exc.__class__.__name__ if empty is None else empty
    try:
        message = str(exc).strip()
    except BaseException:
        return fallback
    return message or fallback


def emit_runtime_warning(
    message: str,
    *,
    stacklevel: int = 2,
) -> None:
    """Emit a runtime warning without allowing warning policy to raise it."""

    try:
        warnings.warn(
            message,
            RuntimeWarning,
            stacklevel=stacklevel + 1,
        )
    except Exception:
        # Warning filters and custom warning hooks are process-global policy.
        # A terminal diagnostic must remain secondary even when that policy
        # promotes or fails the warning.
        return
