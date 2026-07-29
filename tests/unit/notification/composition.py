from pathlib import Path

from nuself.config import (
    EmailConfig,
    EmailSmtpConfig,
    MacosNotificationConfig,
    SystemConfig,
)
from nuself.notification.composition import build_notification_adapters


def test_composition_builds_configured_adapters_in_canonical_order(
    tmp_path: Path,
) -> None:
    config = SystemConfig(
        email=EmailConfig(
            enabled=True,
            smtp=EmailSmtpConfig(
                username="owner",
                password="secret",
            ),
            from_address="from@example.com",
            to_address="to@example.com",
        ),
        macos_notification=MacosNotificationConfig(enabled=True),
    )

    adapters = build_notification_adapters(tmp_path, config=config)

    assert [adapter.delivery_id for adapter in adapters] == [
        "email",
        "macos",
    ]


def test_composition_uses_log_only_when_no_external_adapter_enabled(
    tmp_path: Path,
) -> None:
    config = SystemConfig(
        email=EmailConfig(enabled=False),
        macos_notification=MacosNotificationConfig(enabled=False),
    )

    adapters = build_notification_adapters(tmp_path, config=config)

    assert [adapter.delivery_id for adapter in adapters] == ["log"]
