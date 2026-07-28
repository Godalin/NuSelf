"""Email notification adapter using SMTP."""

from __future__ import annotations

import smtplib
from collections.abc import Mapping
from email.message import EmailMessage
from pathlib import Path
from typing import cast

from nuself.notification import OutboxEntry
from nuself.runtime.observability import (
    report_observed_failure,
    run_observed_best_effort,
)

EmailConfig = dict[str, str | int | bool]


class EmailConfigError(ValueError):
    """Declared private email configuration failure."""


class EmailNotificationAdapter:
    """Deliver outbox entries as emails via SMTP.

    Configuration is read from ``private/email.toml`` under the project root.
    The file is ignored by Git and must be created manually.

    Example ``private/email.toml``::

        [smtp]
        host = "smtp.gmail.com"
        port = 587
        user = "user@gmail.com"
        password = "app-password"

        [notification]
        from = "nuself@localhost"
        to = "user@example.com"
    """

    def __init__(self, project_root: Path | None = None, *, dry_run: bool = False) -> None:
        from nuself.config import runtime_paths
        from nuself.logs import write_log_event

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._dry_run = dry_run
        self._write_log = write_log_event
        self._config = self._load_config()

    def send(self, entry: OutboxEntry) -> bool:
        if self._dry_run:
            self._write_log(
                "outbox",
                "email_dry_run",
                f"{entry.title}: {entry.body}",
                project_root=self._project_root,
                metadata={
                    "entry_id": entry.id,
                    "idempotency_key": entry.idempotency_key,
                    "to": self._config.get("to") if self._config else None,
                },
            )
            return True

        if not self._config:
            report_observed_failure(
                RuntimeError("email configuration is not available"),
                component="outbox",
                event="email_no_config",
                message="Email config not found; skipping delivery",
                project_root=self._project_root,
                level="warning",
                status="failed",
                metadata={"entry_id": entry.id},
            )
            return False

        msg = EmailMessage()
        msg["Subject"] = entry.title
        msg["From"] = self._config["from"]
        msg["To"] = self._config["to"]
        msg.set_content(entry.body)

        if entry.deep_link is not None:
            msg.add_alternative(
                f'<html><body><p>{entry.body}</p><p><a href="{entry.deep_link}">Open</a></p></body></html>',
                subtype="html",
            )

        try:
            host = str(self._config["host"])
            port = int(self._config["port"])
            with smtplib.SMTP(host, port, timeout=30) as server:
                if bool(self._config.get("use_tls", True)):
                    server.starttls()
                user = self._config.get("user")
                password = self._config.get("password")
                if isinstance(user, str) and isinstance(password, str):
                    server.login(user, password)
                server.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            report_observed_failure(
                exc,
                component="outbox",
                event="email_failed",
                message="Email delivery failed",
                project_root=self._project_root,
                level="warning",
                status="failed",
                metadata={"entry_id": entry.id},
            )
            return False

        return True

    def _load_config(self) -> EmailConfig | None:
        config_path = self._project_root / "private" / "email.toml"
        if not config_path.exists():
            return None

        return run_observed_best_effort(
            lambda: _decode_email_config(config_path),
            component="outbox",
            event="email_config_invalid",
            message="Email configuration is invalid; delivery is disabled",
            project_root=self._project_root,
            metadata={"record": config_path.name},
            errors=(EmailConfigError,),
        )


def _decode_email_config(config_path: Path) -> EmailConfig:
    """Decode one present email config without exposing values in errors."""

    import tomllib

    try:
        with config_path.open("rb") as file:
            data: dict[str, object] = tomllib.load(file)
    except OSError:
        raise EmailConfigError(
            "email configuration could not be read"
        ) from None
    except tomllib.TOMLDecodeError:
        raise EmailConfigError(
            "email configuration TOML is malformed"
        ) from None

    smtp = _require_table(data, "smtp")
    notification = _require_table(data, "notification")

    config: EmailConfig = {
        "host": _require_nonempty_string(smtp, "host", section="smtp"),
        "from": _require_nonempty_string(
            notification,
            "from",
            section="notification",
        ),
        "to": _require_nonempty_string(
            notification,
            "to",
            section="notification",
        ),
    }

    port = smtp.get("port")
    if type(port) is not int or not 1 <= port <= 65_535:
        raise EmailConfigError(
            "email configuration smtp.port must be an integer from 1 to 65535"
        )
    config["port"] = port

    use_tls = smtp.get("use_tls")
    if use_tls is not None:
        if not isinstance(use_tls, bool):
            raise EmailConfigError(
                "email configuration smtp.use_tls must be a boolean"
            )
        config["use_tls"] = use_tls

    user = smtp.get("user")
    password = smtp.get("password")
    if (user is None) != (password is None):
        raise EmailConfigError(
            "email configuration smtp.user and smtp.password must be provided together"
        )
    if user is not None and password is not None:
        if not isinstance(user, str) or not user.strip():
            raise EmailConfigError(
                "email configuration smtp.user must be a non-empty string"
            )
        if not isinstance(password, str) or not password.strip():
            raise EmailConfigError(
                "email configuration smtp.password must be a non-empty string"
            )
        config["user"] = user
        config["password"] = password

    return config


def _require_table(
    data: Mapping[str, object],
    key: str,
) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise EmailConfigError(
            f"email configuration [{key}] must be a table"
        )
    return cast(dict[str, object], value)


def _require_nonempty_string(
    data: Mapping[str, object],
    key: str,
    *,
    section: str,
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EmailConfigError(
            f"email configuration {section}.{key} must be a non-empty string"
        )
    return value
