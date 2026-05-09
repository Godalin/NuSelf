"""Tests for deep link parsing and resolution."""

from __future__ import annotations

import pytest

from nuself.notification.deep_link import DeepLink


def test_parse_basic() -> None:
    link = DeepLink.parse("nuself://thread/my-thread")
    assert link.thread_id == "my-thread"
    assert link.message is None


def test_parse_with_message() -> None:
    link = DeepLink.parse("nuself://thread/my-thread?message=hello%20world")
    assert link.thread_id == "my-thread"
    assert link.message == "hello world"


def test_parse_invalid_scheme() -> None:
    with pytest.raises(ValueError, match="unsupported deep link scheme"):
        DeepLink.parse("https://example.com/thread/my-thread")


def test_parse_invalid_path() -> None:
    with pytest.raises(ValueError, match="unsupported deep link path"):
        DeepLink.parse("nuself://memory/my-thread")


def test_parse_missing_thread_id() -> None:
    with pytest.raises(ValueError, match="missing thread id"):
        DeepLink.parse("nuself://thread/")


def test_to_url_basic() -> None:
    link = DeepLink(thread_id="my-thread")
    assert link.to_url() == "nuself://thread/my-thread"


def test_to_url_with_message() -> None:
    link = DeepLink(thread_id="my-thread", message="hello world")
    assert link.to_url() == "nuself://thread/my-thread?message=hello%20world"


def test_roundtrip() -> None:
    original = DeepLink(thread_id="abc-123", message="test message")
    parsed = DeepLink.parse(original.to_url())
    assert parsed.thread_id == original.thread_id
    assert parsed.message == original.message
