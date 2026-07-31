from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import stat

from _pytest.monkeypatch import MonkeyPatch

from nuself.conversation import ConversationMessage, ConversationState
from conversation_fixtures import ConversationStore
from nuself.cli.repl import transcript
from nuself.cli.repl.session import InteractiveSession


def test_transcript_module_owns_export_command_and_progress(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("default"))
    session = InteractiveSession(connected_at=datetime.now(UTC))
    assert session.start_index_for(tmp_path, "default") == 0
    store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content="preserve literal token=example-value",
                ),
                ConversationMessage(role="assistant", content="hi"),
            ],
        )
    )
    copied: list[str] = []

    def copy_text(text: str) -> tuple[bool, str]:
        copied.append(text)
        return True, ""

    monkeypatch.setattr(transcript, "copy_text_to_clipboard", copy_text)

    result = transcript.handle_interactive_export_command(
        ":export",
        tmp_path,
        "default",
        session,
    )

    assert result.startswith("Saved transcript:")
    assert "Copied transcript to clipboard." in result
    assert len(copied) == 1
    assert "preserve literal token=example-value" in copied[0]
    transcript_dir = tmp_path / "transcripts"
    [transcript_path] = transcript_dir.iterdir()
    assert stat.S_IMODE(transcript_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(transcript_path.stat().st_mode) == 0o600
    assert (
        "preserve literal token=example-value"
        in transcript_path.read_text(encoding="utf-8")
    )
    assert session.conversation_ids_with_unexported_messages(tmp_path) == []


def test_invalid_export_option_does_not_create_transcript(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("default"))
    session = InteractiveSession(connected_at=datetime.now(UTC))

    result = transcript.handle_interactive_export_command(
        ":export unknown",
        tmp_path,
        "default",
        session,
    )

    assert ":export [all] [noclip]" in result
    assert not (tmp_path / "transcripts").exists()
