from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

import json
from pathlib import Path

import pytest

from nuself.cli import main
from nuself.cli.exit_codes import CliExitCode
from nuself.memory.model import MemoryEntry
from nuself.logs import read_log_events
from nuself.memory.repository import MemoryEntryRepository
from tests.backend import owned_backend, close_owned_backend


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
    memory_entry_repository(authority).save(entry)
    close_owned_backend(authority)

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
    repo = memory_entry_repository(authority)
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
    close_owned_backend(authority)

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
    assert memory_entry_repository(authority).get(entry.id).title == "After"
    event = read_log_events(
        project_root=authority,
        component="daemon",
    )[-1]
    assert event.event == "data_record_updated"
    assert event.metadata == {
        "collection": "memory_entries",
        "record_id": entry.id,
    }


def test_data_check_reports_unique_invalid_records_and_repair_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authority = _set_home(tmp_path, monkeypatch)
    backend = memory_entry_repository(authority)
    healthy = backend.save(
        MemoryEntry(type="belief", title="Healthy", body="Keep this.")
    )
    close_owned_backend(authority)
    owned_backend(authority).collection("memory_entries").put(
        "mem broken",
        {"id": "mem broken", "body": "private invalid contents"},
    )
    close_owned_backend(authority)

    assert main(["data", "check", "memory"]) == CliExitCode.FAILURE
    output = capsys.readouterr().out
    assert "Checked 2 memory record(s): 1 valid, 1 invalid." in output
    assert "Invalid: mem broken" in output
    assert "nuself data edit memory 'mem broken'" in output
    assert "nuself data delete memory 'mem broken'" in output
    assert "private invalid contents" not in output
    assert healthy.id not in output


def test_data_check_succeeds_for_valid_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authority = _set_home(tmp_path, monkeypatch)
    memory_entry_repository(authority).save(
        MemoryEntry(type="belief", title="Healthy", body="All good.")
    )
    close_owned_backend(authority)

    assert main(["data", "check", "memory"]) == CliExitCode.SUCCESS
    assert "1 valid, 0 invalid" in capsys.readouterr().out


def test_data_edit_rejects_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authority = _set_home(tmp_path, monkeypatch)
    entry = memory_entry_repository(authority).save(
        MemoryEntry(type="belief", title="Stable", body="Keep the id.")
    )
    edited = entry.to_wire()
    edited["id"] = "mem_replaced"
    edit_file = tmp_path / "invalid.json"
    edit_file.write_text(json.dumps(edited), encoding="utf-8")
    close_owned_backend(authority)

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
    assert memory_entry_repository(authority).get(entry.id).title == "Stable"


def test_data_internal_collections_are_hidden_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_home(tmp_path, monkeypatch)
    assert main(["init"]) == 0
    capsys.readouterr()

    assert main(["data", "list", "scheduler_state"]) == 1
    assert "requires --internal" in capsys.readouterr().err


@pytest.mark.parametrize("control", [EOFError(), KeyboardInterrupt()])
def test_data_delete_control_cancels_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    control: BaseException,
) -> None:
    authority = _set_home(tmp_path, monkeypatch)
    repo = memory_entry_repository(authority)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Keep",
            body="Terminal control must not delete this.",
        )
    )
    close_owned_backend(authority)

    def interrupt(_prompt: str) -> str:
        raise control

    monkeypatch.setattr("builtins.input", interrupt)

    assert (
        main(["data", "delete", "memory", entry.id])
        is CliExitCode.INTERRUPTED
    )
    assert memory_entry_repository(authority).get(entry.id) is not None
    assert "Cancelled." in capsys.readouterr().out
