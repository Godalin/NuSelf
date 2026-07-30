from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nuself.scope import (
    NuSelfScope,
    ScopeSelectionError,
    resolve_runtime_paths,
    resolve_scope,
)


def test_default_scope_is_user_home_independent_of_cwd(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first_cwd = tmp_path / "one"
    second_cwd = tmp_path / "two"

    first = resolve_scope(cwd=first_cwd, user_home=home, environ={})
    second = resolve_scope(cwd=second_cwd, user_home=home, environ={})

    assert first == second
    assert first.kind == "user"
    assert first.root == home / ".nuself"
    assert first.user_root == home / ".nuself"
    assert first.workspace_root is None


def test_existing_workspace_directory_does_not_change_default_scope(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "workspace"
    (cwd / ".nuself").mkdir(parents=True)

    scope = resolve_scope(cwd=cwd, user_home=home, environ={})

    assert scope.kind == "user"
    assert scope.root == home / ".nuself"


def test_local_scope_uses_only_current_directory(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    cwd = parent / "nested"
    (parent / ".nuself").mkdir(parents=True)
    cwd.mkdir()

    scope = resolve_scope(local=True, cwd=cwd, environ={})

    assert scope.kind == "workspace"
    assert scope.workspace_root == cwd
    assert scope.root == cwd / ".nuself"


def test_workspace_scope_canonicalizes_explicit_path(tmp_path: Path) -> None:
    workspace = tmp_path / "one" / ".." / "project"

    scope = resolve_scope(workspace=workspace, cwd=tmp_path, environ={})

    expected = (tmp_path / "project").resolve()
    assert scope.workspace_root == expected
    assert scope.root == expected / ".nuself"


def test_nuself_home_overrides_only_user_authority(tmp_path: Path) -> None:
    custom = (tmp_path / "custom").resolve()
    user = resolve_scope(
        user_home=tmp_path / "ignored",
        environ={"NUSELF_HOME": str(custom)},
    )
    workspace = resolve_scope(
        local=True,
        cwd=tmp_path / "project",
        environ={"NUSELF_HOME": str(custom)},
    )

    assert user.root == custom
    assert workspace.root == (tmp_path / "project").resolve() / ".nuself"
    assert workspace.user_root == custom


@pytest.mark.parametrize("value", ["", " ", "relative/path"])
def test_invalid_nuself_home_fails_closed(
    tmp_path: Path,
    value: str,
) -> None:
    with pytest.raises(ScopeSelectionError):
        resolve_scope(
            cwd=tmp_path,
            user_home=tmp_path / "home",
            environ={"NUSELF_HOME": value},
        )


def test_local_and_workspace_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(
        ScopeSelectionError,
        match="cannot be used together",
    ):
        resolve_scope(local=True, workspace=tmp_path, environ={})


def test_authority_id_is_stable_and_scope_sensitive(tmp_path: Path) -> None:
    root = tmp_path / "same"
    user = resolve_scope(
        user_home=root.parent,
        environ={"NUSELF_HOME": str(root)},
    )
    repeated = resolve_scope(
        user_home=root.parent,
        environ={"NUSELF_HOME": str(root)},
    )
    workspace = resolve_scope(workspace=root.parent, environ={})

    assert user.authority_id == repeated.authority_id
    assert user.authority_id.startswith("v1-")
    assert user.authority_id != workspace.authority_id


def test_scope_is_frozen(tmp_path: Path) -> None:
    scope = resolve_scope(user_home=tmp_path, environ={})

    with pytest.raises(FrozenInstanceError):
        setattr(scope, "root", tmp_path)


def test_runtime_paths_derive_every_location_from_selected_authority(
    tmp_path: Path,
) -> None:
    user_root = (tmp_path / "user").resolve()
    workspace_root = (tmp_path / "project").resolve()
    scope = resolve_scope(
        workspace=workspace_root,
        environ={"NUSELF_HOME": str(user_root)},
    )

    paths = resolve_runtime_paths(scope)

    assert paths.scope is scope
    assert paths.authority_root == workspace_root / ".nuself"
    assert paths.config_file == workspace_root / ".nuself" / "config.yaml"
    assert paths.user_config_file == user_root / "config.yaml"
    assert paths.database_file == workspace_root / ".nuself" / "nuself.sqlite"
    assert paths.sources_dir == workspace_root / ".nuself" / "sources"
    assert paths.logs_dir == workspace_root / ".nuself" / "logs"
    assert paths.exports_dir == workspace_root / ".nuself" / "exports"
    assert paths.imports_dir == workspace_root / ".nuself" / "imports"
    assert paths.runtime_dir == workspace_root / ".nuself" / "runtime"
    assert paths.socket_path == workspace_root / ".nuself" / "runtime" / "nuself.sock"


def test_scope_rejects_incoherent_manual_construction(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workspace root"):
        NuSelfScope(
            kind="workspace",
            root=tmp_path.resolve() / ".nuself",
            user_root=(tmp_path / "home").resolve(),
            authority_id="v1-test",
        )
