"""Email notification adapter using SMTP."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from nuself.notification import OutboxEntry


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
            self._write_log(
                "outbox",
                "email_no_config",
                "Email config not found; skipping delivery.",
                project_root=self._project_root,
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
            self._write_log(
                "outbox",
                "email_failed",
                str(exc),
                project_root=self._project_root,
                metadata={"entry_id": entry.id},
            )
            return False

        return True

    def _load_config(self) -> dict[str, str | int | bool] | None:
        config_path = self._project_root / "private" / "email.toml"
        if not config_path.exists():
            return None
        import tomllib

        try:
            with config_path.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return None

        smtp = data.get("smtp", {})
        notification = data.get("notification", {})
        config: dict[str, str | int | bool] = {}
        for key in ("host", "user", "password"):
            val = smtp.get(key)
            if isinstance(val, str):
                config[key] = val
        port = smtp.get("port")
        if isinstance(port, int):
            config["port"] = port
        use_tls = smtp.get("use_tls")
        if isinstance(use_tls, bool):
            config["use_tls"] = use_tls
        for key in ("from", "to"):
            val = notification.get(key)
            if isinstance(val, str):
                config[key] = val

        required = {"host", "port", "from", "to"}
        if not required.issubset(config.keys()):
            return None
        return config
