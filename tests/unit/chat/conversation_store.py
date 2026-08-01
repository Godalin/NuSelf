# pyright: reportPrivateUsage=false
"""Tests for ConversationStore thread management operations."""

from __future__ import annotations

import multiprocessing
import threading
import time
from multiprocessing.context import SpawnContext
from multiprocessing.synchronize import Event
from pathlib import Path

import pytest

from nuself.conversation import ConversationMessage, ConversationState
from nuself.conversation import _PendingTurn
from nuself.storage import auto_backend
from conversation_fixtures import ConversationStore
from tests.backend import owned_backend


def _hold_thread_lock(
    project_root: str,
    conversation_id: str,
    ready: Event,
    release: Event,
) -> None:
    root = Path(project_root)
    backend = auto_backend(root)
    try:
        store = ConversationStore(root, backend=backend)
        with store._locked(conversation_id):
            ready.set()
            if not release.wait(timeout=10):
                raise RuntimeError("parent did not release thread lock")
    finally:
        backend.close()


def _hold_thread_update(
    project_root: str,
    ready: Event,
    release: Event,
) -> None:
    root = Path(project_root)
    backend = auto_backend(root)
    store = ConversationStore(root, backend=backend)

    def update(state: ConversationState) -> tuple[ConversationState, None]:
        ready.set()
        if not release.wait(timeout=10):
            raise RuntimeError("parent did not release conversation update")
        return (
            ConversationState(
                conversation_id=state.conversation_id,
                summary=state.summary,
                messages=[
                    *state.messages,
                    ConversationMessage(role="user", content="latest"),
                ],
                message_start_index=state.message_start_index,
                next_message_index=state.next_message_index + 1,
            ),
            None,
        )

    try:
        store.update("source", update)
    finally:
        backend.close()


def _run_thread_lifecycle(
    project_root: str,
    operation: str,
    attempted: Event,
    done: Event,
) -> None:
    root = Path(project_root)
    backend = auto_backend(root)
    try:
        store = ConversationStore(root, backend=backend)
        attempted.set()
        if operation == "rename":
            store.rename("source", "target")
        elif operation == "branch":
            store.branch("source", "target")
        elif operation == "archive":
            store.archive("source")
        elif operation == "unarchive":
            store.unarchive("source")
        elif operation == "delete":
            store.delete("source")
        else:
            raise AssertionError(f"unknown lifecycle operation: {operation}")
        done.set()
    finally:
        backend.close()


def _spawn_context() -> SpawnContext:
    return multiprocessing.get_context("spawn")


def test_list_returns_empty_when_no_threads(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    assert store.list() == []


def test_update_does_not_hold_sqlite_lock_across_callback(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path)
    backend = owned_backend(tmp_path)
    completed = threading.Event()

    def read_from_worker() -> None:
        backend.collection("memory_entries").list()
        completed.set()

    def update(state: ConversationState) -> tuple[ConversationState, None]:
        worker = threading.Thread(target=read_from_worker)
        worker.start()
        worker.join(timeout=2)
        assert completed.is_set()
        return state, None

    store.update("default", update)


def test_update_rejects_direct_concurrent_conversation_change(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path)
    collection = owned_backend(tmp_path).collection("conversations")

    def update(state: ConversationState) -> tuple[ConversationState, None]:
        collection.put(
            "default",
            ConversationState.empty("default").to_wire(),
        )
        return state, None

    with pytest.raises(ValueError, match="changed concurrently"):
        store.update("default", update)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("message_start_index", True),
        ("next_message_index", False),
    ],
)
def test_thread_state_rejects_boolean_message_indexes(
    field_name: str,
    value: object,
) -> None:
    wire: dict[str, object] = {
        "conversation_id": "strict",
        "summary": "",
        "messages": [],
        "message_start_index": 0,
        "next_message_index": 0,
    }
    wire[field_name] = value

    with pytest.raises(ValueError, match="index"):
        ConversationState.from_wire(wire)


def test_conversation_state_rejects_non_object_message_member() -> None:
    with pytest.raises(ValueError, match="every conversation message"):
        ConversationState.from_wire(
            {
                "conversation_id": "strict",
                "summary": "",
                "messages": [
                    {"role": "user", "content": "kept"},
                    "silently dropped before",
                ],
                "message_start_index": 0,
                "next_message_index": 2,
            }
        )


def test_thread_state_rejects_inconsistent_absolute_index() -> None:
    with pytest.raises(ValueError, match="message count"):
        ConversationState.from_wire(
            {
                "conversation_id": "strict",
                "summary": "",
                "messages": [{"role": "user", "content": "one"}],
                "message_start_index": 4,
                "next_message_index": 6,
            }
        )


def test_thread_state_derives_missing_legacy_next_index() -> None:
    state = ConversationState.from_wire(
        {
            "conversation_id": "legacy",
            "summary": "",
            "messages": [{"role": "user", "content": "one"}],
            "message_start_index": 4,
        }
    )

    assert state.message_start_index == 4
    assert state.next_message_index == 5


def test_thread_message_rejects_unknown_wire_field() -> None:
    with pytest.raises(ValueError, match="unsupported fields"):
        ConversationMessage.from_wire(
            {
                "role": "user",
                "content": "one",
                "unexpected": "value",
            }
        )


def test_list_returns_conversation_ids(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("alpha"))
    store.save(ConversationState.empty("beta"))
    assert store.list() == ["alpha", "beta"]


def test_list_ignores_lock_files(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("only"))
    lock_path = tmp_path / "runtime" / "conversation-locks" / "only.lock"
    lock_path.write_text("lock")
    assert store.list() == ["only"]


def test_list_ignores_archived_threads(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("active"))
    store.archive("active")  # archive removes from root
    store.save(ConversationState.empty("active"))  # recreate active
    assert store.list() == ["active"]


def test_rename_moves_thread_file(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("old"))
    store.rename("old", "new")
    assert store.list() == ["new"]
    loaded = store.load("new")
    assert loaded.conversation_id == "new"


def test_rename_preserves_messages_and_summary(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    state = ConversationState(
        conversation_id="old",
        summary="prior summary",
        messages=[ConversationMessage(role="user", content="hello")],
        message_start_index=0,
        next_message_index=1,
    )
    store.save(state)
    store.rename("old", "new")
    loaded = store.load("new")
    assert loaded.summary == "prior summary"
    assert len(loaded.messages) == 1
    assert loaded.messages[0].content == "hello"
    assert loaded.message_start_index == 0
    assert loaded.next_message_index == 1


def test_rename_waits_for_update_and_moves_latest_snapshot(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("source"))
    context = _spawn_context()
    update_ready = context.Event()
    release_update = context.Event()
    attempted = context.Event()
    rename_done = context.Event()
    updater = context.Process(
        target=_hold_thread_update,
        args=(str(tmp_path), update_ready, release_update),
    )
    renamer = context.Process(
        target=_run_thread_lifecycle,
        args=(str(tmp_path), "rename", attempted, rename_done),
    )
    updater.start()
    assert update_ready.wait(timeout=10)
    renamer.start()
    try:
        assert attempted.wait(timeout=10)
        assert not rename_done.wait(timeout=0.2)
    finally:
        release_update.set()
        updater.join(timeout=10)
        renamer.join(timeout=10)
        for process in (updater, renamer):
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    assert updater.exitcode == 0
    assert renamer.exitcode == 0
    assert store.load("target").messages[-1].content == "latest"
    assert (
        tmp_path / "runtime" / "conversation-locks" / "source.lock"
    ).exists()
    assert (
        tmp_path / "runtime" / "conversation-locks" / "target.lock"
    ).exists()


def test_rename_same_id_is_noop(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("same"))
    store.rename("same", "same")
    assert store.list() == ["same"]


def test_rename_missing_thread_raises(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    try:
        store.rename("missing", "new")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "missing" in str(exc)


def test_rename_to_existing_thread_raises(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("a"))
    store.save(ConversationState.empty("b"))
    try:
        store.rename("a", "b")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "b" in str(exc)


def test_branch_copies_all_messages_by_default(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    source = ConversationState(
        conversation_id="source",
        summary="summary",
        messages=[
            ConversationMessage(role="user", content="a"),
            ConversationMessage(role="assistant", content="b"),
        ],
        message_start_index=0,
        next_message_index=2,
    )
    store.save(source)
    branched = store.branch("source", "fork")
    assert branched.conversation_id == "fork"
    assert len(branched.messages) == 2
    assert branched.next_message_index == 2
    loaded = store.load("fork")
    assert loaded.summary == "summary"


def test_branch_at_specific_index(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    source = ConversationState(
        conversation_id="source",
        summary="summary",
        messages=[
            ConversationMessage(role="user", content="a"),
            ConversationMessage(role="assistant", content="b"),
            ConversationMessage(role="user", content="c"),
        ],
        message_start_index=5,
        next_message_index=8,
    )
    store.save(source)
    branched = store.branch("source", "fork", message_index=2)
    assert len(branched.messages) == 2
    assert branched.messages[0].content == "a"
    assert branched.messages[1].content == "b"
    assert branched.message_start_index == 5
    assert branched.next_message_index == 7


def test_branch_at_zero_index(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    source = ConversationState(
        conversation_id="source",
        summary="summary",
        messages=[ConversationMessage(role="user", content="a")],
        message_start_index=3,
        next_message_index=4,
    )
    store.save(source)
    branched = store.branch("source", "fork", message_index=0)
    assert len(branched.messages) == 0
    assert branched.next_message_index == 3


@pytest.mark.parametrize(
    ("operation", "held_conversation_id"),
    [
        ("rename", "source"),
        ("rename", "target"),
        ("branch", "source"),
        ("branch", "target"),
        ("archive", "source"),
        ("unarchive", "source"),
        ("delete", "source"),
    ],
)
def test_lifecycle_operations_wait_for_cross_process_thread_locks(
    tmp_path: Path,
    operation: str,
    held_conversation_id: str,
) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("source"))
    if operation == "unarchive":
        store.archive("source")
    context = _spawn_context()
    lock_ready = context.Event()
    release_lock = context.Event()
    attempted = context.Event()
    done = context.Event()
    owner = context.Process(
        target=_hold_thread_lock,
        args=(
            str(tmp_path),
            held_conversation_id,
            lock_ready,
            release_lock,
        ),
    )
    lifecycle = context.Process(
        target=_run_thread_lifecycle,
        args=(str(tmp_path), operation, attempted, done),
    )
    owner.start()
    assert lock_ready.wait(timeout=10)
    lifecycle.start()
    try:
        assert attempted.wait(timeout=10)
        assert not done.wait(timeout=0.2)
    finally:
        release_lock.set()
        owner.join(timeout=10)
        lifecycle.join(timeout=10)
        for process in (owner, lifecycle):
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    assert owner.exitcode == 0
    assert lifecycle.exitcode == 0
    assert (
        tmp_path
        / "runtime"
        / "conversation-locks"
        / f"{held_conversation_id}.lock"
    ).exists()


def test_load_uses_committed_snapshot_while_write_transaction_is_held(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path)
    expected = ConversationState.empty("default")
    store.save(expected)
    context = _spawn_context()
    lock_ready = context.Event()
    release_lock = context.Event()
    owner = context.Process(
        target=_hold_thread_update,
        args=(str(tmp_path), lock_ready, release_lock),
    )
    owner.start()
    assert lock_ready.wait(timeout=10)
    try:
        started_at = time.monotonic()
        actual = store.load("default")
        elapsed = time.monotonic() - started_at
    finally:
        release_lock.set()
        owner.join(timeout=10)
        if owner.is_alive():
            owner.terminate()
            owner.join(timeout=10)

    assert owner.exitcode == 0
    assert actual == expected
    assert elapsed < 1.0


def test_branch_missing_source_raises(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    try:
        store.branch("missing", "fork")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "missing" in str(exc)


def test_branch_to_existing_raises(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("source"))
    store.save(ConversationState.empty("fork"))
    try:
        store.branch("source", "fork")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "fork" in str(exc)


def test_branch_out_of_range_raises(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(
        ConversationState(
            conversation_id="source",
            messages=[ConversationMessage(role="user", content="a")],
        )
    )
    try:
        store.branch("source", "fork", message_index=5)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "out of range" in str(exc)


def test_thread_lifecycle_preserves_or_excludes_pending_turns(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path)
    pending = _PendingTurn.from_message("turn-1", "unfinished")
    store.save(
        ConversationState(
            conversation_id="source",
            messages=[ConversationMessage(role="user", content="earlier")],
            pending_turns=(pending,),
        )
    )

    store.rename("source", "renamed")
    assert store.load("renamed").pending_turns == (pending,)
    branch = store.branch("renamed", "branch")
    assert branch.pending_turns == ()
    store.archive("renamed")
    assert store.load("renamed").pending_turns == (pending,)


def test_archive_moves_thread_to_subdir(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("old"))
    store.archive("old")
    assert store.list() == []
    assert store.list_archived() == ["old"]
    assert store.load("old").archived is True


def test_archive_missing_thread_raises(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    try:
        store.archive("missing")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "missing" in str(exc)


def test_archive_idempotent_on_already_archived_is_error(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(ConversationState.empty("old"))
    store.archive("old")
    try:
        store.archive("old")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "already exists" in str(exc)
