from __future__ import annotations

# pyright: reportPrivateUsage=false

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import stat

import pytest

from nuself.cli import main
from nuself.layout_migration import LayoutMigrationError, migrate_legacy_layout
from nuself.scope import resolve_scope
from nuself.storage import (
    FileStorageBackend,
    _create_sqlite_backend,
    auto_backend,
)
from nuself.storage_sqlite import SqliteStorageBackend


def _migrate_in_process(source: str, workspace: str) -> str:
    scope = resolve_scope(workspace=Path(workspace), environ={})
    try:
        migrate_legacy_layout(Path(source), scope)
    except FileExistsError:
        return "existing"
    return "published"


def test_file_layout_is_atomically_published_and_source_is_preserved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-private"
    source.mkdir()
    backend = FileStorageBackend(source)
    backend.collection("memory_entries").put(
        "mem-legacy",
        {"id": "mem-legacy", "title": "Legacy memory"},
    )
    backend.close()
    (source / "config.yaml").write_text(
        "chat:\n  language_preference: zh-CN\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = resolve_scope(workspace=workspace, environ={})

    target = migrate_legacy_layout(source, scope)

    assert target == workspace / ".nuself"
    assert source.is_dir()
    assert (source / "config.yaml").is_file()
    assert (target / "config.yaml").is_file()
    migrated = auto_backend(target)
    try:
        assert migrated.collection("memory_entries").get("mem-legacy") == {
            "id": "mem-legacy",
            "title": "Legacy memory",
        }
    finally:
        assert isinstance(migrated, FileStorageBackend | SqliteStorageBackend)
        migrated.close()
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert stat.S_IMODE((target / "config.yaml").stat().st_mode) == 0o600


def test_transient_runtime_and_lock_files_are_not_migrated(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-private"
    runtime = source / "runtime"
    runtime.mkdir(parents=True)
    (source / ".storage-authority.lock").write_text(
        "stale-source-lock",
        encoding="utf-8",
    )
    (runtime / "nuself.pid").write_text("123", encoding="utf-8")
    (runtime / "nuself.lock").write_text("", encoding="utf-8")
    (runtime / "nuself.sock").write_text("", encoding="utf-8")
    (runtime / "cursor.json").write_text("{}", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    target = migrate_legacy_layout(
        source,
        resolve_scope(workspace=workspace, environ={}),
    )

    assert (
        target / ".storage-authority.lock"
    ).read_text(encoding="utf-8") != "stale-source-lock"
    assert not (target / "runtime" / "nuself.pid").exists()
    assert not (target / "runtime" / "nuself.lock").exists()
    assert not (target / "runtime" / "nuself.sock").exists()
    assert (target / "runtime" / "cursor.json").is_file()


def test_concurrent_migration_publishes_exactly_once(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-private"
    source.mkdir()
    (source / "config.yaml").write_text("{}\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with ProcessPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                _migrate_in_process,
                [str(source)] * 4,
                [str(workspace)] * 4,
            )
        )

    assert results.count("published") == 1
    assert results.count("existing") == 3
    assert (workspace / ".nuself" / "config.yaml").is_file()
    assert not list(workspace.glob(".nuself.migrating-*"))


def test_live_sqlite_layout_uses_backup_and_keeps_wal_data(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-private"
    source.mkdir()
    backend = _create_sqlite_backend(
        source,
        db_path=source / "nuself.sqlite",
    )
    backend.collection("memory_entries").put(
        "mem-wal",
        {"id": "mem-wal", "title": "Committed in WAL"},
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = resolve_scope(workspace=workspace, environ={})
    try:
        target = migrate_legacy_layout(source, scope)
    finally:
        backend.close()

    migrated = auto_backend(target)
    try:
        assert migrated.collection("memory_entries").get("mem-wal") == {
            "id": "mem-wal",
            "title": "Committed in WAL",
        }
    finally:
        assert isinstance(migrated, FileStorageBackend | SqliteStorageBackend)
        migrated.close()
    assert (source / "nuself.sqlite").is_file()


def test_existing_target_is_rejected_without_source_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-private"
    source.mkdir()
    sentinel = source / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    workspace = tmp_path / "workspace"
    target = workspace / ".nuself"
    target.mkdir(parents=True)
    target_sentinel = target / "existing.txt"
    target_sentinel.write_text("existing", encoding="utf-8")
    scope = resolve_scope(workspace=workspace, environ={})

    with pytest.raises(FileExistsError, match="already exists"):
        migrate_legacy_layout(source, scope)

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert target_sentinel.read_text(encoding="utf-8") == "existing"


def test_source_symlink_is_rejected_without_target_creation(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    source = tmp_path / "legacy-private"
    source.symlink_to(external, target_is_directory=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = resolve_scope(workspace=workspace, environ={})

    with pytest.raises(LayoutMigrationError, match="actual directory"):
        migrate_legacy_layout(source, scope)

    assert not (workspace / ".nuself").exists()
    assert list(external.iterdir()) == []


def test_nested_source_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "legacy-private"
    source.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (source / "redirect").symlink_to(external, target_is_directory=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = resolve_scope(workspace=workspace, environ={})

    with pytest.raises(LayoutMigrationError, match="contains a symlink"):
        migrate_legacy_layout(source, scope)

    assert not (workspace / ".nuself").exists()


def test_cli_migrates_to_explicit_workspace_and_reports_preserved_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "private"
    source.mkdir()
    (source / "config.yaml").write_text("{}\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = main(
        [
            "migrate-layout",
            "--from",
            str(source),
            "--workspace",
            str(workspace),
        ]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert f"Migrated legacy layout to workspace authority: {workspace / '.nuself'}" in output
    assert f"Source preserved: {source}" in output
