from __future__ import annotations

from pathlib import Path
import stat

import pytest
from pydantic import ValidationError

from nuself.config.settings import ConfigSystem
from nuself.config.scope import resolve_scope


def _write_config(root: Path, content: str) -> Path:
    root.mkdir(parents=True, mode=0o700)
    path = root / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_user_scope_loads_only_user_configuration(tmp_path: Path) -> None:
    user_root = tmp_path / "user"
    _write_config(
        user_root,
        "chat:\n  language_preference: zh-CN\n",
    )
    scope = resolve_scope(environ={"NUSELF_HOME": str(user_root.resolve())})

    config = ConfigSystem.load_scope(scope)

    assert config.chat.language_preference == "zh-CN"


def test_workspace_mapping_recursively_overrides_user_defaults(
    tmp_path: Path,
) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    _write_config(
        user_root,
        (
            "chat:\n"
            "  language_preference: zh-CN\n"
            "  context:\n"
            "    recent_messages: 20\n"
            "    summary_target_chars: 3000\n"
            "reflection:\n"
            "  auto_notify: true\n"
        ),
    )
    _write_config(
        workspace / ".nuself",
        (
            "chat:\n"
            "  context:\n"
            "    recent_messages: 7\n"
            "reflection:\n"
            "  auto_notify: false\n"
        ),
    )
    scope = resolve_scope(
        workspace=workspace,
        environ={"NUSELF_HOME": str(user_root.resolve())},
    )

    config = ConfigSystem.load_scope(scope)

    assert config.chat.language_preference == "zh-CN"
    assert config.chat.context.recent_messages == 7
    assert config.chat.context.summary_target_chars == 3000
    assert config.reflection.auto_notify is False


def test_workspace_sequence_replaces_user_sequence(tmp_path: Path) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    _write_config(
        user_root,
        (
            "llm:\n"
            "  - base_url: https://user-one.example/v1\n"
            "    model: user-one\n"
            "  - base_url: https://user-two.example/v1\n"
            "    model: user-two\n"
        ),
    )
    _write_config(
        workspace / ".nuself",
        (
            "llm:\n"
            "  - base_url: https://workspace.example/v1\n"
            "    model: workspace\n"
        ),
    )
    scope = resolve_scope(
        workspace=workspace,
        environ={"NUSELF_HOME": str(user_root.resolve())},
    )

    config = ConfigSystem.load_scope(scope)

    assert [endpoint.model for endpoint in config.llm.endpoints] == [
        "workspace"
    ]


def test_invalid_workspace_override_fails_final_validation(
    tmp_path: Path,
) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    _write_config(user_root, "chat:\n  language_preference: zh-CN\n")
    _write_config(
        workspace / ".nuself",
        "chat:\n  request_timeout_seconds: 0\n",
    )
    scope = resolve_scope(
        workspace=workspace,
        environ={"NUSELF_HOME": str(user_root.resolve())},
    )

    with pytest.raises(ValidationError):
        ConfigSystem.load_scope(scope)


def test_missing_workspace_config_keeps_user_layer(tmp_path: Path) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_config(
        user_root,
        "chat:\n  language_preference: zh-TW\n",
    )
    scope = resolve_scope(
        workspace=workspace,
        environ={"NUSELF_HOME": str(user_root.resolve())},
    )

    config = ConfigSystem.load_scope(scope)

    assert config.chat.language_preference == "zh-TW"
    assert not (workspace / ".nuself").exists()


def test_layer_reads_harden_managed_roots_and_files(tmp_path: Path) -> None:
    user_root = tmp_path / "user"
    workspace_root = tmp_path / "workspace" / ".nuself"
    user_config = _write_config(user_root, "{}\n")
    workspace_config = _write_config(workspace_root, "{}\n")
    user_root.chmod(0o755)
    workspace_root.chmod(0o755)
    user_config.chmod(0o644)
    workspace_config.chmod(0o644)
    scope = resolve_scope(
        workspace=tmp_path / "workspace",
        environ={"NUSELF_HOME": str(user_root.resolve())},
    )

    ConfigSystem.load_scope(scope)

    assert stat.S_IMODE(user_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(workspace_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(user_config.stat().st_mode) == 0o600
    assert stat.S_IMODE(workspace_config.stat().st_mode) == 0o600


def test_symlinked_workspace_authority_is_rejected_without_target_changes(
    tmp_path: Path,
) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    external = tmp_path / "external"
    workspace.mkdir()
    external.mkdir(mode=0o755)
    external.chmod(0o755)
    external_config = external / "config.yaml"
    external_config.write_text("{}\n", encoding="utf-8")
    external_config.chmod(0o644)
    (workspace / ".nuself").symlink_to(external, target_is_directory=True)
    scope = resolve_scope(
        workspace=workspace,
        environ={"NUSELF_HOME": str(user_root.resolve())},
    )

    with pytest.raises(OSError, match="actual directory"):
        ConfigSystem.load_scope(scope)

    assert stat.S_IMODE(external.stat().st_mode) == 0o755
    assert stat.S_IMODE(external_config.stat().st_mode) == 0o644
