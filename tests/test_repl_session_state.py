from datetime import UTC, datetime
from pathlib import Path

from nuself.cli.repl.input import InteractiveInput
from nuself.cli.repl.session import InteractiveSession


def test_interactive_input_instances_do_not_share_mutable_objects(
    tmp_path: Path,
) -> None:
    first = InteractiveInput(tmp_path / "first")
    second = InteractiveInput(tmp_path / "second")

    assert first.history is not second.history
    assert first.completer is not second.completer


def test_header_suppression_is_scoped_to_session() -> None:
    first = InteractiveSession(connected_at=datetime.now(UTC))
    second = InteractiveSession(connected_at=datetime.now(UTC))

    assert first.should_render_header(
        thread_id="default",
        daemon_status="running",
    )
    assert not first.should_render_header(
        thread_id="default",
        daemon_status="running",
    )
    assert second.should_render_header(
        thread_id="default",
        daemon_status="running",
    )
