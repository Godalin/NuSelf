"""Tests for thought pack export/import/inspect."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import stat

import pytest

from nuself.cli import main
from nuself.storage import set_default_backend
from nuself.storage_sqlite import COLLECTION_NAMES, SqliteStorageBackend


def _create_pack_schema(path: Path, *, version: int) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE _schema_version (version INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO _schema_version VALUES (?)",
            (version,),
        )
        for name in COLLECTION_NAMES:
            connection.execute(
                f'CREATE TABLE "col_{name}" '
                "(id TEXT PRIMARY KEY)"
            )
        connection.commit()
    finally:
        connection.close()


def test_pack_export_creates_sqlite(tmp_path: Path) -> None:
    # Create source database via migration
    assert main(["--project-root", str(tmp_path), "dev", "migrate"]) == 0
    db = tmp_path / "private" / "nuself.sqlite"
    assert db.exists()

    # Export
    assert main(["--project-root", str(tmp_path), "pack", "export", "test-pack"]) == 0
    export = tmp_path / "private" / "exports" / "test-pack.sqlite"
    assert export.exists()
    assert export.stat().st_size > 0
    assert stat.S_IMODE(export.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(export.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "name",
    (
        "../escaped",
        "nested/escaped",
        "/tmp/escaped",
        ".hidden",
        "..",
        "",
        "CON",
        "con.sqlite",
        "NUL.backup",
        "COM1",
        "lpt9.archive",
        "file.",
    ),
)
def test_pack_export_rejects_path_like_names(
    tmp_path: Path,
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--project-root", str(tmp_path), "dev", "migrate"]) == 0
    capsys.readouterr()

    assert main(
        ["--project-root", str(tmp_path), "pack", "export", name]
    ) == 1

    assert "Invalid pack name" in capsys.readouterr().err
    assert not (tmp_path / "private" / "escaped.sqlite").exists()


def test_pack_export_fails_without_db(tmp_path: Path) -> None:
    result = main(["--project-root", str(tmp_path), "pack", "export", "no-db"])
    assert result != 0


def test_pack_export_includes_live_wal_data(tmp_path: Path) -> None:
    backend = SqliteStorageBackend(
        tmp_path / "private" / "nuself.sqlite",
        project_root=tmp_path,
    )
    set_default_backend(backend, tmp_path)
    backend.collection("memory_entries").put(
        "live-entry",
        {"id": "live-entry", "title": "Live WAL data"},
    )

    assert main(
        [
            "--project-root",
            str(tmp_path),
            "pack",
            "export",
            "live",
        ]
    ) == 0

    snapshot = SqliteStorageBackend(
        tmp_path / "private" / "exports" / "live.sqlite"
    )
    try:
        assert snapshot.collection("memory_entries").get(
            "live-entry"
        ) == {
            "id": "live-entry",
            "title": "Live WAL data",
        }
    finally:
        snapshot.close()


def test_pack_import_copies_file(tmp_path: Path) -> None:
    # Create a "foreign" database
    foreign = tmp_path / "friend-thoughts.sqlite"
    from nuself.storage import create_sqlite_backend
    be = create_sqlite_backend(db_path=foreign)
    try:
        be.collection("memory_entries").put(
            "mem_001",
            {"id": "mem_001", "title": "Friend's thought"},
        )
    finally:
        be.close()

    assert main(["--project-root", str(tmp_path), "pack", "import", str(foreign)]) == 0
    imported = tmp_path / "private" / "imports" / "friend-thoughts.sqlite"
    assert imported.exists()
    assert stat.S_IMODE(imported.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(imported.stat().st_mode) == 0o600


def test_pack_import_rejects_duplicate(tmp_path: Path) -> None:
    foreign = tmp_path / "thoughts.sqlite"
    from nuself.storage import create_sqlite_backend
    create_sqlite_backend(db_path=foreign).close()

    assert main(["--project-root", str(tmp_path), "pack", "import", str(foreign)]) == 0
    result = main(["--project-root", str(tmp_path), "pack", "import", str(foreign)])
    assert result != 0


def test_pack_import_rejects_non_sqlite(tmp_path: Path) -> None:
    f = tmp_path / "data.txt"
    f.write_text("not a database")
    result = main(["--project-root", str(tmp_path), "pack", "import", str(f)])
    assert result != 0


def test_pack_import_rejects_corrupt_sqlite_without_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "corrupt.sqlite"
    source.write_bytes(b"not a sqlite database")

    result = main(
        ["--project-root", str(tmp_path), "pack", "import", str(source)]
    )

    assert result == 1
    assert not (
        tmp_path / "private" / "imports" / source.name
    ).exists()


def test_pack_import_rejects_foreign_and_partial_schemas(
    tmp_path: Path,
) -> None:
    foreign = tmp_path / "foreign.sqlite"
    connection = sqlite3.connect(foreign)
    connection.execute("CREATE TABLE notes (id TEXT PRIMARY KEY)")
    connection.commit()
    connection.close()
    partial = tmp_path / "partial.sqlite"
    _create_pack_schema(partial, version=2)
    connection = sqlite3.connect(partial)
    connection.execute("DROP TABLE col_memory_entries")
    connection.commit()
    connection.close()

    assert main(
        ["--project-root", str(tmp_path), "pack", "import", str(foreign)]
    ) == 1
    assert main(
        ["--project-root", str(tmp_path), "pack", "import", str(partial)]
    ) == 1


def test_pack_import_rejects_future_schema_without_mutating_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "future.sqlite"
    _create_pack_schema(source, version=99)

    assert main(
        ["--project-root", str(tmp_path), "pack", "import", str(source)]
    ) == 1

    connection = sqlite3.connect(source)
    try:
        assert connection.execute(
            "SELECT MAX(version) FROM _schema_version"
        ).fetchone() == (99,)
    finally:
        connection.close()


def test_pack_import_accepts_legacy_schema_without_mutating_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.sqlite"
    _create_pack_schema(source, version=1)

    assert main(
        ["--project-root", str(tmp_path), "pack", "import", str(source)]
    ) == 0

    imported = tmp_path / "private" / "imports" / source.name
    for path in (source, imported):
        connection = sqlite3.connect(path)
        try:
            assert connection.execute(
                "SELECT MAX(version) FROM _schema_version"
            ).fetchone() == (1,)
        finally:
            connection.close()


def test_pack_import_includes_source_wal_data(tmp_path: Path) -> None:
    source = tmp_path / "live.sqlite"
    backend = SqliteStorageBackend(source)
    backend.collection("memory_entries").put(
        "wal-import",
        {"id": "wal-import", "title": "Live import"},
    )
    try:
        assert main(
            [
                "--project-root",
                str(tmp_path),
                "pack",
                "import",
                str(source),
            ]
        ) == 0
    finally:
        backend.close()

    imported = SqliteStorageBackend(
        tmp_path / "private" / "imports" / source.name
    )
    try:
        assert imported.collection("memory_entries").get(
            "wal-import"
        ) == {
            "id": "wal-import",
            "title": "Live import",
        }
    finally:
        imported.close()


def test_pack_inspect_shows_summary(tmp_path: Path) -> None:
    from nuself.storage import create_sqlite_backend
    db = tmp_path / "pack.sqlite"
    be = create_sqlite_backend(db_path=db)
    try:
        be.collection("memory_entries").put(
            "mem_001",
            {"id": "mem_001", "type": "belief"},
        )
    finally:
        be.close()

    from nuself.cli import main
    assert main(["--project-root", str(tmp_path), "pack", "inspect", str(db)]) == 0


def test_pack_inspect_defaults_to_main_db(tmp_path: Path) -> None:
    # Without a path, it should fall back to main db
    result = main(["--project-root", str(tmp_path), "pack", "inspect"])
    assert result != 0  # no main db yet

    # After migration, it should succeed
    assert main(["--project-root", str(tmp_path), "dev", "migrate"]) == 0
    assert main(["--project-root", str(tmp_path), "pack", "inspect"]) == 0


def test_pack_inspect_preserves_legacy_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "legacy-inspect.sqlite"
    _create_pack_schema(source, version=1)
    before = source.read_bytes()

    assert main(
        ["--project-root", str(tmp_path), "pack", "inspect", str(source)]
    ) == 0

    assert source.read_bytes() == before
    assert "Thought pack: legacy-inspect.sqlite" in capsys.readouterr().out


def test_pack_inspect_rejects_invalid_pack(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "invalid.sqlite"
    source.write_bytes(b"invalid")

    assert main(
        ["--project-root", str(tmp_path), "pack", "inspect", str(source)]
    ) == 1

    assert "Invalid thought pack:" in capsys.readouterr().err


def test_pack_inspect_counts_live_wal_data(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "live-inspect.sqlite"
    backend = SqliteStorageBackend(source)
    backend.collection("memory_entries").put(
        "live",
        {"id": "live", "title": "Live"},
    )
    try:
        assert main(
            [
                "--project-root",
                str(tmp_path),
                "pack",
                "inspect",
                str(source),
            ]
        ) == 0
    finally:
        backend.close()

    output = capsys.readouterr().out
    assert "memory_entries: 1 items" in output
    assert "total items: 1" in output
