from pathlib import Path

import pytest

from nuself.cli.repl.presentation import SessionHeaderPresenter


def test_session_header_presenter_uses_current_status_every_time(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    statuses = iter(("one-shot", "running"))
    roots: list[Path | None] = []

    def daemon_status(project_root: Path | None) -> str:
        roots.append(project_root)
        return next(statuses)

    presenter = SessionHeaderPresenter(daemon_status)

    presenter.show(tmp_path, "first")
    presenter.show(tmp_path, "second")

    assert roots == [tmp_path, tmp_path]
    assert capsys.readouterr().out.splitlines() == [
        "[daemon] session status=one-shot thread=first",
        "[daemon] session status=running thread=second",
    ]
