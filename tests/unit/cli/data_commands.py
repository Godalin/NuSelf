from __future__ import annotations

import json
from pathlib import Path

import pytest

from nuself.cli import main
from nuself.domain.memory import MemoryEntry
from nuself.logs import read_log_events
from nuself.memory.repository import MemoryEntryRepository
from nuself.storage import reset_default_backend


def _set_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    authority = tmp_path / "home"
    monkeypatch.setenv("NUSELF_HOME", str(authority))
    return authority


def test_data_lists_and_shows_public_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authority = _set_home(tmp_path, monkeypatch)
    entry = MemoryEntry(
        type="belief",
        title="Visible memory",
        body="Authoritative data is inspectable.",
    )
    MemoryEntryRepository(authority).save(entry)
    reset_default_backend(authority)

    assert main(["data", "list", "memory", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["id"] == entry.id
    assert listed["title"] == "Visible memory"

    assert main(["data", "show", "memory", entry.id, "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["body"] == "Authoritative data is inspectable."


def test_data_edit_validates_and_audits_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authority = _set_home(tmp_path, monkeypatch)
    repo = MemoryEntryRepository(authority)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Before",
            body="Edit this through the supported interface.",
        )
    )
    edited = entry.to_wire()
    edited["title"] = "After"
    edit_file = tmp_path / "edited.json"
    edit_file.write_text(json.dumps(edited), encoding="utf-8")
    reset_default_backend(authority)

    assert (
        main(
            [
                "data",
                "edit",
                "memory",
                entry.id,
                "--file",
                str(edit_file),
                "--yes",
            ]
        )
        == 0
    )
    assert "Updated memory/" in capsys.readouterr().out
    assert MemoryEntryRepository(authority).get(entry.id).title == "After"
    event = read_log_events(
        project_root=authority,
        component="daemon",
    )[-1]
    assert event.event == "data_record_updated"
    assert event.metadata == {
        "collection": "memory_entries",
        "record_id": entry.id,
    }


def test_data_edit_rejects_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authority = _set_home(tmp_path, monkeypatch)
    entry = MemoryEntryRepository(authority).save(
        MemoryEntry(type="belief", title="Stable", body="Keep the id.")
    )
    edited = entry.to_wire()
    edited["id"] = "mem_replaced"
    edit_file = tmp_path / "invalid.json"
    edit_file.write_text(json.dumps(edited), encoding="utf-8")
    reset_default_backend(authority)

    assert (
        main(
            [
                "data",
                "edit",
                "memory",
                entry.id,
                "--file",
                str(edit_file),
                "--yes",
            ]
        )
        == 1
    )
    assert "cannot change its stable identity" in capsys.readouterr().err
    assert MemoryEntryRepository(authority).get(entry.id).title == "Stable"


def test_data_internal_collections_are_hidden_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(tmp_path, monkeypatch)

    assert main(["data", "list", "scheduler_state"]) == 1
    assert "requires --internal" in capsys.readouterr().err
