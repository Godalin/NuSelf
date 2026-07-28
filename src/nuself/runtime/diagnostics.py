"""Terminal diagnostics that must never replace a primary outcome."""

from __future__ import annotations

import re
import warnings


_BEARER_CREDENTIAL_RE = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
_AUTHORIZATION_VALUE_RE = re.compile(
    r"(?P<prefix>[\"']?authorization[\"']?\s*[:=]\s*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n,;]+)",
    re.IGNORECASE,
)
_LABELED_CREDENTIAL_RE = re.compile(
    r"(?P<prefix>[\"']?"
    r"(?:api[_-]?key|access[_-]?token|client[_-]?secret|"
    r"password|secret|token)"
    r"[\"']?\s*[:=]\s*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}&]+)",
    re.IGNORECASE,
)
_RAW_CREDENTIAL_RE = re.compile(
    r"\b(?:sk-(?:proj-|ant-)?|xox[baprs]-|gh[pousr]_)[A-Za-z0-9._-]{8,}\b"
    r"|\bAKIA[0-9A-Z]{16}\b",
)


def redact_sensitive_text(message: str) -> str:
    """Remove common credential forms from diagnostic text."""

    redacted = _RAW_CREDENTIAL_RE.sub("***", message)
    redacted = _BEARER_CREDENTIAL_RE.sub("Bearer ***", redacted)
    redacted = _AUTHORIZATION_VALUE_RE.sub(
        _redact_labeled_value,
        redacted,
    )
    return _LABELED_CREDENTIAL_RE.sub(_redact_labeled_value, redacted)


def _redact_labeled_value(match: re.Match[str]) -> str:
    value = match.group("value")
    replacement = (
        f"{value[0]}***{value[-1]}"
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"
        else "***"
    )
    return f"{match.group('prefix')}{replacement}"


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


def diagnostic_exception_message(exc: BaseException) -> str:
    """Return safe, credential-sanitized text for one exception."""

    return redact_sensitive_text(safe_exception_message(exc))


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
