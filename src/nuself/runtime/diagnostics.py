"""Terminal diagnostics that must never replace a primary outcome."""

from __future__ import annotations

import warnings


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
