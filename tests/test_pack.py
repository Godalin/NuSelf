"""Tests for thought pack export/import/inspect."""

from __future__ import annotations

from pathlib import Path

from nuself.cli import main


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


def test_pack_export_fails_without_db(tmp_path: Path) -> None:
    result = main(["--project-root", str(tmp_path), "pack", "export", "no-db"])
    assert result != 0


def test_pack_import_copies_file(tmp_path: Path) -> None:
    # Create a "foreign" database
    foreign = tmp_path / "friend-thoughts.sqlite"
    from nuself.storage import create_sqlite_backend
    be = create_sqlite_backend(db_path=foreign)
    be.collection("memory_entries").put("mem_001", {"id": "mem_001", "title": "Friend's thought"})

    assert main(["--project-root", str(tmp_path), "pack", "import", str(foreign)]) == 0
    imported = tmp_path / "private" / "imports" / "friend-thoughts.sqlite"
    assert imported.exists()


def test_pack_import_rejects_duplicate(tmp_path: Path) -> None:
    foreign = tmp_path / "thoughts.sqlite"
    from nuself.storage import create_sqlite_backend
    create_sqlite_backend(db_path=foreign)

    assert main(["--project-root", str(tmp_path), "pack", "import", str(foreign)]) == 0
    result = main(["--project-root", str(tmp_path), "pack", "import", str(foreign)])
    assert result != 0


def test_pack_import_rejects_non_sqlite(tmp_path: Path) -> None:
    f = tmp_path / "data.txt"
    f.write_text("not a database")
    result = main(["--project-root", str(tmp_path), "pack", "import", str(f)])
    assert result != 0


def test_pack_inspect_shows_summary(tmp_path: Path) -> None:
    from nuself.storage import create_sqlite_backend
    db = tmp_path / "pack.sqlite"
    be = create_sqlite_backend(db_path=db)
    be.collection("memory_entries").put("mem_001", {"id": "mem_001", "type": "belief"})

    from nuself.cli import main
    assert main(["--project-root", str(tmp_path), "pack", "inspect", str(db)]) == 0


def test_pack_inspect_defaults_to_main_db(tmp_path: Path) -> None:
    # Without a path, it should fall back to main db
    result = main(["--project-root", str(tmp_path), "pack", "inspect"])
    assert result != 0  # no main db yet

    # After migration, it should succeed
    assert main(["--project-root", str(tmp_path), "dev", "migrate"]) == 0
    assert main(["--project-root", str(tmp_path), "pack", "inspect"]) == 0
