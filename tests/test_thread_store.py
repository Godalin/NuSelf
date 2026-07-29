# pyright: reportPrivateUsage=false
"""Tests for ThreadStore thread management operations."""

from __future__ import annotations

import multiprocessing
from multiprocessing.context import SpawnContext
from multiprocessing.synchronize import Event
from pathlib import Path

import pytest

from nuself.agent.chat import ThreadState, ThreadStore, ThreadMessage


def _hold_thread_lock(
    project_root: str,
    thread_id: str,
    ready: Event,
    release: Event,
) -> None:
    store = ThreadStore(Path(project_root))
    with store._locked(thread_id):
        ready.set()
        if not release.wait(timeout=10):
            raise RuntimeError("parent did not release thread lock")


def _hold_thread_update(
    project_root: str,
    ready: Event,
    release: Event,
) -> None:
    store = ThreadStore(Path(project_root))

    def update(state: ThreadState) -> tuple[ThreadState, None]:
        ready.set()
        if not release.wait(timeout=10):
            raise RuntimeError("parent did not release thread update")
        return (
            ThreadState(
                thread_id=state.thread_id,
                summary=state.summary,
                messages=[
                    *state.messages,
                    ThreadMessage(role="user", content="latest"),
                ],
                message_start_index=state.message_start_index,
                next_message_index=state.next_message_index + 1,
            ),
            None,
        )

    store.update("source", update)


def _run_thread_lifecycle(
    project_root: str,
    operation: str,
    attempted: Event,
    done: Event,
) -> None:
    store = ThreadStore(Path(project_root))
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


def _spawn_context() -> SpawnContext:
    return multiprocessing.get_context("spawn")


def test_list_returns_empty_when_no_threads(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    assert store.list() == []


def test_list_returns_thread_ids(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("alpha"))
    store.save(ThreadState.empty("beta"))
    assert store.list() == ["alpha", "beta"]


def test_list_ignores_lock_files(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("only"))
    lock_path = tmp_path / "private" / "threads" / "only.lock"
    lock_path.write_text("lock")
    assert store.list() == ["only"]


def test_list_ignores_archived_threads(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("active"))
    store.archive("active")  # archive removes from root
    store.save(ThreadState.empty("active"))  # recreate active
    assert store.list() == ["active"]


def test_rename_moves_thread_file(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("old"))
    store.rename("old", "new")
    assert store.list() == ["new"]
    loaded = store.load("new")
    assert loaded.thread_id == "new"


def test_rename_preserves_messages_and_summary(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    state = ThreadState(
        thread_id="old",
        summary="prior summary",
        messages=[ThreadMessage(role="user", content="hello")],
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
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("source"))
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
        tmp_path / "private" / "threads" / "source.lock"
    ).exists()
    assert (
        tmp_path / "private" / "threads" / "target.lock"
    ).exists()


def test_rename_same_id_is_noop(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("same"))
    store.rename("same", "same")
    assert store.list() == ["same"]


def test_rename_missing_thread_raises(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    try:
        store.rename("missing", "new")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "missing" in str(exc)


def test_rename_to_existing_thread_raises(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("a"))
    store.save(ThreadState.empty("b"))
    try:
        store.rename("a", "b")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "b" in str(exc)


def test_branch_copies_all_messages_by_default(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    source = ThreadState(
        thread_id="source",
        summary="summary",
        messages=[
            ThreadMessage(role="user", content="a"),
            ThreadMessage(role="assistant", content="b"),
        ],
        message_start_index=0,
        next_message_index=2,
    )
    store.save(source)
    branched = store.branch("source", "fork")
    assert branched.thread_id == "fork"
    assert len(branched.messages) == 2
    assert branched.next_message_index == 2
    loaded = store.load("fork")
    assert loaded.summary == "summary"


def test_branch_at_specific_index(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    source = ThreadState(
        thread_id="source",
        summary="summary",
        messages=[
            ThreadMessage(role="user", content="a"),
            ThreadMessage(role="assistant", content="b"),
            ThreadMessage(role="user", content="c"),
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
    store = ThreadStore(tmp_path)
    source = ThreadState(
        thread_id="source",
        summary="summary",
        messages=[ThreadMessage(role="user", content="a")],
        message_start_index=3,
        next_message_index=4,
    )
    store.save(source)
    branched = store.branch("source", "fork", message_index=0)
    assert len(branched.messages) == 0
    assert branched.next_message_index == 3


@pytest.mark.parametrize(
    ("operation", "held_thread_id"),
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
    held_thread_id: str,
) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("source"))
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
            held_thread_id,
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
        / "private"
        / "threads"
        / f"{held_thread_id}.lock"
    ).exists()


def test_branch_missing_source_raises(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    try:
        store.branch("missing", "fork")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "missing" in str(exc)


def test_branch_to_existing_raises(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("source"))
    store.save(ThreadState.empty("fork"))
    try:
        store.branch("source", "fork")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "fork" in str(exc)


def test_branch_out_of_range_raises(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(
        ThreadState(
            thread_id="source",
            messages=[ThreadMessage(role="user", content="a")],
        )
    )
    try:
        store.branch("source", "fork", message_index=5)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "out of range" in str(exc)


def test_archive_moves_thread_to_subdir(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("old"))
    store.archive("old")
    assert store.list() == []
    archived_path = tmp_path / "private" / "threads" / "archived" / "old.json"
    assert archived_path.exists()


def test_archive_missing_thread_raises(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    try:
        store.archive("missing")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "missing" in str(exc)


def test_archive_idempotent_on_already_archived_is_error(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("old"))
    store.archive("old")
    try:
        store.archive("old")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not found" in str(exc)
