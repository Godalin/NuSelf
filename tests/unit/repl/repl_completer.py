# pyright: reportPrivateUsage=false
"""Tests for REPL tab completion using prompt_toolkit Completer API."""

from __future__ import annotations

from pathlib import Path

import pytest
from prompt_toolkit.document import Document

from nuself.conversation import ConversationState
from conversation_fixtures import ConversationStore
from nuself.cli import _InteractiveCompleter
from nuself.logs import read_log_events
from nuself.reason.repository import ReasonRepository


def test_completer_suggests_commands(tmp_path: Path) -> None:
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":co", cursor_position=3)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert ":conversation" in texts


def test_completer_suggests_conversation_ids(tmp_path: Path) -> None:
    ConversationStore(tmp_path).save(ConversationState.empty("alpha"))
    ConversationStore(tmp_path).save(ConversationState.empty("beta"))
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":conversation a", cursor_position=15)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert "alpha" in texts


def test_completer_empty_for_non_command(tmp_path: Path) -> None:
    completer = _InteractiveCompleter(tmp_path)
    doc = Document("hello", cursor_position=5)
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 0


def test_completer_multiple_command_matches(tmp_path: Path) -> None:
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":mem", cursor_position=4)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert ":memory" not in texts
    assert ":mem" in texts


def test_completer_suggests_archived_conversation_ids(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("alpha"))
    store.save(ConversationState.empty("beta"))
    store.archive("alpha")
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":unarchive a", cursor_position=12)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert "alpha" in texts


@pytest.mark.parametrize(
    ("method_name", "command", "completion_kind"),
    [
        ("list", ":conversation a", "conversations"),
        ("list_archived", ":unarchive a", "archived_conversations"),
    ],
)
def test_conversation_completion_failure_is_observed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    command: str,
    completion_kind: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("conversation index unavailable")

    store = ConversationStore(tmp_path)
    monkeypatch.setattr(store, method_name, fail)

    def selected_store(project_root: Path | None) -> ConversationStore:
        del project_root
        return store

    monkeypatch.setattr(
        "nuself.cli.repl.input.compose_cli_conversation_store",
        selected_store,
    )
    completer = _InteractiveCompleter(tmp_path)

    completions = list(
        completer.get_completions(
            Document(command, cursor_position=len(command)),
            None,
        )
    )

    assert completions == []
    event = read_log_events(project_root=tmp_path, component="chat")[-1]
    assert event.event == "completion_load_failed"
    assert event.error == "conversation index unavailable"
    assert event.metadata == {"completion": completion_kind}


def test_reason_completion_failure_is_observed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("reason index unavailable")

    monkeypatch.setattr(ReasonRepository, "list_threads", fail)
    command = ":reason show a"
    completer = _InteractiveCompleter(tmp_path)

    completions = list(
        completer.get_completions(
            Document(command, cursor_position=len(command)),
            None,
        )
    )

    assert completions == []
    event = read_log_events(
        project_root=tmp_path,
        component="reasoning",
    )[-1]
    assert event.event == "completion_load_failed"
    assert event.error == "reason index unavailable"
    assert event.metadata == {}
