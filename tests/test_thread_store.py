"""Tests for ThreadStore thread management operations."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat import ThreadState, ThreadStore, ThreadMessage


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
