"""Terminal diagnostics that must never replace a primary outcome."""

from __future__ import annotations

import re
import warnings
from collections.abc import Mapping
from typing import cast


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
_SENSITIVE_METADATA_KEYS = frozenset(
    {
        "access_token",
        "accesstoken",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "clientsecret",
        "cookie",
        "credential",
        "credentials",
        "password",
        "private_key",
        "privatekey",
        "refresh_token",
        "refreshtoken",
        "secret",
        "set_cookie",
        "setcookie",
        "token",
    }
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


def sanitize_diagnostic_metadata(
    metadata: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Copy and recursively sanitize persisted diagnostic metadata."""

    if metadata is None:
        return None
    sanitized = _sanitize_diagnostic_value(metadata)
    if not isinstance(sanitized, dict):
        raise TypeError("diagnostic metadata must be a mapping")
    return cast(dict[str, object], sanitized)


def _sanitize_diagnostic_value(value: object) -> object:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        source = cast(Mapping[object, object], value)
        mapping: dict[str, object] = {}
        for key, item in source.items():
            if not isinstance(key, str):
                return source
            sanitized_key = redact_sensitive_text(key)
            mapping[sanitized_key] = (
                "***"
                if _is_sensitive_metadata_key(key)
                else _sanitize_diagnostic_value(item)
            )
        return mapping
    if isinstance(value, list | tuple):
        items = cast(list[object] | tuple[object, ...], value)
        return [_sanitize_diagnostic_value(item) for item in items]
    return value


def _is_sensitive_metadata_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    leaf = normalized.rsplit(".", maxsplit=1)[-1]
    return leaf in _SENSITIVE_METADATA_KEYS


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


def diagnostic_exception_message(
    exc: BaseException,
    *,
    empty: str | None = None,
) -> str:
    """Return safe, credential-sanitized text for one exception."""

    return redact_sensitive_text(safe_exception_message(exc, empty=empty))


def diagnostic_exception_chain(exc: BaseException) -> str:
    """Return one safe, sanitized compact exception chain."""

    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        message = safe_exception_message(current)
        if message not in messages:
            messages.append(message)
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__suppress_context__:
            current = None
        else:
            current = current.__context__
    return redact_sensitive_text(" <- ".join(messages))


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
