from __future__ import annotations

from pathlib import Path
import stat

import pytest

from nuself.cli import build_parser, main


def test_scope_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["--local", "--workspace", str(tmp_path), "dev", "paths"]
        )


def test_default_init_uses_nuself_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_root = tmp_path / "custom-user-root"
    monkeypatch.setenv("NUSELF_HOME", str(user_root))

    assert main(["init"]) == 0

    assert user_root.is_dir()
    assert stat.S_IMODE(user_root.stat().st_mode) == 0o700
    for name in ("sources", "logs", "exports", "imports", "runtime"):
        assert (user_root / name).is_dir()
    assert not (user_root / "nuself.sqlite").exists()
    assert str(user_root) in capsys.readouterr().out


def test_workspace_init_uses_explicit_dot_nuself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("NUSELF_HOME", str(tmp_path / "user"))

    assert main(["--workspace", str(workspace), "init"]) == 0

    assert (workspace / ".nuself").is_dir()
    assert not (tmp_path / "user").exists()


def test_local_init_does_not_search_parent_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    nested = parent / "nested"
    (parent / ".nuself").mkdir(parents=True)
    nested.mkdir()
    monkeypatch.chdir(nested)
    monkeypatch.setenv("NUSELF_HOME", str(tmp_path / "user"))

    assert main(["--local", "init"]) == 0

    assert (nested / ".nuself").is_dir()


def test_dev_paths_is_read_only_and_reports_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("NUSELF_HOME", str(user_root))

    assert main(["--workspace", str(workspace), "dev", "paths"]) == 0

    output = capsys.readouterr().out
    assert "scope: workspace" in output
    assert f"authority_root: {workspace / '.nuself'}" in output
    assert f"  - {user_root / 'config.yaml'} (missing)" in output
    assert not user_root.exists()
    assert not (workspace / ".nuself").exists()


def test_dev_config_uses_layered_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user_root.mkdir()
    (workspace / ".nuself").mkdir(parents=True)
    (user_root / "config.yaml").write_text(
        "chat:\n  language_preference: zh-CN\n",
        encoding="utf-8",
    )
    (workspace / ".nuself" / "config.yaml").write_text(
        "chat:\n  context:\n    recent_messages: 6\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NUSELF_HOME", str(user_root))

    assert main(
        ["--workspace", str(workspace), "dev", "config"]
    ) == 0

    output = capsys.readouterr().out
    assert "chat.language_preference: zh-CN" in output
    assert "chat.context.recent_messages: 6" in output
