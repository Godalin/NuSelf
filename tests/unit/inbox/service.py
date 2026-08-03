"""Inbox domain contracts."""

from pathlib import Path

from nuself.config.settings import runtime_paths
from nuself.inbox.model import InboxItem
from nuself.inbox.service import InboxService
from nuself.storage.authority import auto_backend


def _service(root: Path) -> InboxService:
    return InboxService(runtime_paths(root), auto_backend(root))


def test_add_is_idempotent_by_source_occurrence(tmp_path: Path) -> None:
    inbox = _service(tmp_path)
    first = inbox.add(InboxItem(
        id="inbox-reflection-1", kind="reflection", source_id="reflection-1",
        title="First", body="One", idempotency_key="reflection-1",
    ))
    second = inbox.add(InboxItem(
        id="inbox-reflection-duplicate", kind="reflection", source_id="reflection-1",
        title="Duplicate", body="Two", idempotency_key="reflection-1",
    ))

    assert second == first
    assert inbox.list() == [first]


def test_attention_state_is_independent_from_source_domain(tmp_path: Path) -> None:
    inbox = _service(tmp_path)
    item = inbox.add(InboxItem(
        id="inbox-reason-1", kind="reason_step", source_id="step-1",
        title="Reason update", body="New conclusion", idempotency_key="step-1",
    ))

    assert inbox.mark_read(item.id).status == "read"
    assert inbox.dismiss(item.id).status == "dismissed"
    assert inbox.resolve(item.id).status == "resolved"


def test_clear_removes_only_terminal_attention_items(tmp_path: Path) -> None:
    inbox = _service(tmp_path)
    for status in ("pending", "read", "dismissed", "resolved"):
        inbox.add(InboxItem(
            id=status, title=status, body=status, status=status,
            idempotency_key=status,
        ))

    assert inbox.clear() == 2
    assert {item.status for item in inbox.list()} == {"pending", "read"}
