from pathlib import Path

from nuself.config.settings import (
    EmailConfig,
    EmailSmtpConfig,
    MacosNotificationConfig,
    runtime_paths,
)
from nuself.notification.composition import build_notification_adapters


def test_composition_builds_configured_adapters_in_canonical_order(
    tmp_path: Path,
) -> None:
    email_config = EmailConfig(
        enabled=True,
        smtp=EmailSmtpConfig(
            username="owner",
            password="secret",
        ),
        from_address="from@example.com",
        to_address="to@example.com",
    )

    adapters = build_notification_adapters(
        runtime_paths(tmp_path),
        email_config=email_config,
        macos_config=MacosNotificationConfig(enabled=True),
    )

    assert isinstance(adapters, tuple)
    assert [adapter.delivery_id for adapter in adapters] == [
        "email",
        "macos",
    ]


def test_composition_uses_log_only_when_no_external_adapter_enabled(
    tmp_path: Path,
) -> None:
    adapters = build_notification_adapters(
        runtime_paths(tmp_path),
        email_config=EmailConfig(enabled=False),
        macos_config=MacosNotificationConfig(enabled=False),
    )

    assert [adapter.delivery_id for adapter in adapters] == ["log"]
