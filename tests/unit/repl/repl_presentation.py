import pytest

from nuself.cli.presentation import print_session_header


def test_print_session_header_renders_resolved_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_session_header("one-shot", "first")
    print_session_header("running", "second")

    assert capsys.readouterr().out.splitlines() == [
        "[daemon] session status=one-shot conversation=first",
        "[daemon] session status=running conversation=second",
    ]
