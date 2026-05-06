from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nuself.cli import main


class CaptureResult(Protocol):
    out: str
    err: str


class CaptureFixture(Protocol):
    def readouterr(self) -> CaptureResult: ...


def test_chat_uses_one_shot_when_daemon_is_missing(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "chat", "--message", "hello"])
    captured = capsys.readouterr()

    assert result == 0
    assert "one-shot runtime received: hello" in captured.out


def test_daemon_status_reports_missing_daemon(tmp_path: Path, capsys: CaptureFixture) -> None:
    result = main(["--project-root", str(tmp_path), "daemon", "status"])
    captured = capsys.readouterr()

    assert result == 1
    assert "daemon stopped" in captured.out


def test_memory_add_list_show_delete(tmp_path: Path, capsys: CaptureFixture) -> None:
    add_result = main(
        [
            "--project-root",
            str(tmp_path),
            "memory",
            "add",
            "--type",
            "belief",
            "--title",
            "Clarity",
            "--body",
            "State assumptions explicitly.",
            "--tag",
            "style",
        ]
    )
    add_output = capsys.readouterr().out
    entry_id = add_output.split(" ", 1)[0]

    list_result = main(["--project-root", str(tmp_path), "memory", "list"])
    list_output = capsys.readouterr().out

    show_result = main(["--project-root", str(tmp_path), "memory", "show", entry_id])
    show_output = capsys.readouterr().out

    delete_result = main(["--project-root", str(tmp_path), "memory", "delete", entry_id])
    delete_output = capsys.readouterr().out

    assert add_result == 0
    assert list_result == 0
    assert show_result == 0
    assert delete_result == 0
    assert "Clarity" in list_output
    assert "State assumptions explicitly." in show_output
    assert f"Deleted memory entry: {entry_id}" in delete_output
