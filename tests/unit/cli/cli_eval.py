from pathlib import Path

from _pytest.capture import CaptureFixture

from nuself.cli import main


def test_dev_eval_notifications_counts_structured_scenarios(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    result = main(
        [
            "--workspace",
            str(tmp_path),
            "dev",
            "eval",
            "--component",
            "notifications",
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "== notifications: 11/11 passed ==" in output
    assert "PASS deep_link/basic-conversation" in output
    assert output.rstrip().endswith("11/11 passed")
