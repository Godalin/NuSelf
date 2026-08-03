"""Canonical delivery-adapter composition root."""

from __future__ import annotations

from nuself.config.settings import EmailConfig, MacosNotificationConfig, RuntimePaths
from nuself.delivery.adapters import (
    DeliveryAdapter,
    LogDeliveryAdapter,
)
from nuself.delivery.email import EmailDeliveryAdapter
from nuself.delivery.macos import MacOSDeliveryAdapter


def build_delivery_adapters(
    paths: RuntimePaths,
    *,
    email_config: EmailConfig,
    macos_config: MacosNotificationConfig,
) -> tuple[DeliveryAdapter, ...]:
    """Build one ordered adapter plan shared by every runtime surface."""

    adapters: list[DeliveryAdapter] = []
    if email_config.enabled:
        adapters.append(
            EmailDeliveryAdapter(
                paths.authority_root,
                config=email_config,
            )
        )
    if macos_config.enabled:
        adapters.append(MacOSDeliveryAdapter(paths.authority_root))
    if not adapters:
        adapters.append(LogDeliveryAdapter(paths.authority_root))
    return tuple(adapters)
