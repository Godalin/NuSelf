from __future__ import annotations

from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import stat

import pytest
from pydantic import ValidationError

from nuself.config import (
    ConfigSystem,
    EmailConfig,
    EmailSmtpConfig,
    LlmEndpointConfig,
    SystemConfig,
    runtime_paths,
)


def test_runtime_paths_are_under_authority_root(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    assert paths.authority_root == tmp_path
    assert paths.runtime_dir == tmp_path / "runtime"
    assert paths.logs_dir == tmp_path / "logs"
    assert paths.socket_path.parent == paths.socket_runtime_dir
    assert paths.socket_path.name == f"{paths.scope.authority_id}.sock"
    assert paths.daemon_lock_path == tmp_path / "runtime" / "nuself.lock"
    assert (
        paths.daemon_process_log_path
        == tmp_path / "logs" / "daemon-process.log"
    )

    with pytest.raises(FrozenInstanceError):
        setattr(paths, "authority_root", tmp_path.parent)


def test_flat_config_redacts_every_endpoint_key_without_aggregate_values(
    tmp_path: Path,
) -> None:
    secret_one = "first-provider-secret"
    secret_two = "second-provider-secret"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        (
            "llm:\n"
            "  - base_url: https://one.example/v1\n"
            f"    api_key: {secret_one}\n"
            "    model: first\n"
            "  - base_url: https://two.example/v1\n"
            f"    api_key: {secret_two}\n"
            "    model: second\n"
        ),
        encoding="utf-8",
    )

    config = ConfigSystem.load(config_path, tmp_path)
    flat = ConfigSystem().as_flat_dict(config)
    rendered = repr(flat)

    assert secret_one not in rendered
    assert secret_two not in rendered
    assert flat["llm.endpoints.0.api_key"] == "***"
    assert flat["llm.endpoints.1.api_key"] == "***"
    assert not any(
        isinstance(value, (dict, list, tuple))
        for value in flat.values()
    )


def test_smtp_password_is_absent_from_flat_projection_and_repr() -> None:
    secret = "smtp-password-must-not-leak"
    config = SystemConfig(
        email=EmailConfig(
            enabled=True,
            smtp=EmailSmtpConfig(
                username="owner",
                password=secret,
            ),
            from_address="from@example.com",
            to_address="to@example.com",
        )
    )

    flat = ConfigSystem().as_flat_dict(config)

    assert flat["email.smtp.password"] == "***"
    assert secret not in repr(flat)
    assert secret not in repr(config)
    assert secret not in repr(config.email)
    assert secret not in repr(config.email.smtp)


def test_api_key_is_absent_from_model_repr() -> None:
    secret = "provider-secret"

    endpoint = LlmEndpointConfig(api_key=secret)

    assert secret not in repr(endpoint)


def test_validation_error_hides_secret_input(tmp_path: Path) -> None:
    secret = "invalid-secret-value"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        (
            "email:\n"
            "  enabled: true\n"
            "  smtp:\n"
            "    port: 0\n"
            "    username: owner\n"
            f"    password: {secret}\n"
            "  from_address: from@example.com\n"
            "  to_address: to@example.com\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as captured:
        ConfigSystem.load(project_root=tmp_path)

    assert secret not in str(captured.value)


@pytest.mark.parametrize(
    "content",
    [
        "- not\n- an\n- object\n",
        "unknown_section: true\n",
        "chat:\n  unknown_field: true\n",
    ],
)
def test_invalid_or_unknown_configuration_fails_explicitly(
    tmp_path: Path,
    content: str,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises((ValueError, ValidationError)):
        ConfigSystem.load(project_root=tmp_path)


@pytest.mark.parametrize("non_finite", [".inf", "-.inf", ".nan"])
@pytest.mark.parametrize(
    "template",
    [
        (
            "llm:\n"
            "  - model: test\n"
            "    timeout_seconds: {value}\n"
        ),
        "chat:\n  request_timeout_seconds: {value}\n",
    ],
)
def test_non_finite_timeouts_are_rejected_before_runtime_clients(
    tmp_path: Path,
    non_finite: str,
    template: str,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        template.format(value=non_finite),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        ConfigSystem.load(project_root=tmp_path)


def test_retired_v025_config_field_is_rejected(
    tmp_path: Path,
) -> None:
    (tmp_path / "config.yaml").write_text(
        "experimental:\n  langmem_adapter: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="langmem_adapter"):
        ConfigSystem.load(project_root=tmp_path)


def test_enabled_email_ignores_legacy_file_and_uses_current_validation(
    tmp_path: Path,
) -> None:
    authority = tmp_path
    config_path = authority / "config.yaml"
    config_path.write_text(
        (
            "email:\n"
            "  enabled: true\n"
            "  smtp:\n"
            "    host: smtp.example.com\n"
            "  from_address: sender@example.com\n"
        ),
        encoding="utf-8",
    )
    legacy_secret = "legacy-email-secret-must-not-leak"
    (authority / "email.toml").write_text(
        (
            "[smtp]\n"
            'user = "owner@example.com"\n'
            f'password = "{legacy_secret}"\n'
            "[notification]\n"
            'to = "recipient@example.com"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as captured:
        ConfigSystem.load(project_root=tmp_path)

    message = str(captured.value)
    assert legacy_secret not in message
    assert "to_address" in message


def test_config_read_hardens_authority_root_and_file(
    tmp_path: Path,
) -> None:
    authority = tmp_path
    authority.chmod(0o755)
    config_path = authority / "config.yaml"
    config_path.write_text("email:\n  enabled: false\n", encoding="utf-8")
    config_path.chmod(0o644)

    ConfigSystem.load(project_root=tmp_path)

    assert stat.S_IMODE(authority.stat().st_mode) == 0o700
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_config_reload_does_not_trust_reused_file_metadata(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "chat:\n  language_preference: en\n",
        encoding="utf-8",
    )
    original_stat = config_path.stat()

    assert (
        ConfigSystem.load(project_root=tmp_path).chat.language_preference
        == "en"
    )

    config_path.write_text(
        "chat:\n  language_preference: fr\n",
        encoding="utf-8",
    )
    os.utime(
        config_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    assert (
        ConfigSystem.load(project_root=tmp_path).chat.language_preference
        == "fr"
    )


def test_config_read_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "external.yaml"
    target.write_text("email:\n  enabled: false\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.symlink_to(target)

    with pytest.raises(OSError, match="regular file"):
        ConfigSystem.load(project_root=tmp_path)
