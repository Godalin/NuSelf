"""Tests for DeepLink parsing and serialization."""

from __future__ import annotations

import pytest

from nuself.notification.deep_link import DeepLink


def test_parse_open_thread() -> None:
    link = DeepLink.parse("nuself://thread/default")
    assert link.action == "open_thread"
    assert link.thread_id == "default"
    assert link.message is None


def test_parse_open_thread_with_message() -> None:
    link = DeepLink.parse("nuself://thread/default?message=hello%20world")
    assert link.action == "open_thread"
    assert link.thread_id == "default"
    assert link.message == "hello world"


def test_parse_new_thread() -> None:
    link = DeepLink.parse("nuself://new-thread?title=My%20Thread&message=hello&candidate_id=c1")
    assert link.action == "new_thread"
    assert link.title == "My Thread"
    assert link.message == "hello"
    assert link.candidate_id == "c1"


def test_parse_new_thread_minimal() -> None:
    link = DeepLink.parse("nuself://new-thread")
    assert link.action == "new_thread"
    assert link.title is None
    assert link.message is None
    assert link.candidate_id is None


def test_to_url_open_thread() -> None:
    link = DeepLink(action="open_thread", thread_id="default")
    assert link.to_url() == "nuself://thread/default"


def test_to_url_open_thread_with_message() -> None:
    link = DeepLink(action="open_thread", thread_id="default", message="hello world")
    assert link.to_url() == "nuself://thread/default?message=hello%20world"


def test_to_url_new_thread() -> None:
    link = DeepLink.for_new_thread(title="My Thread", message="hello", candidate_id="c1")
    url = link.to_url()
    assert url.startswith("nuself://new-thread?")
    assert "title=My%20Thread" in url
    assert "message=hello" in url
    assert "candidate_id=c1" in url


def test_to_url_new_thread_minimal() -> None:
    link = DeepLink.for_new_thread()
    assert link.to_url() == "nuself://new-thread"


def test_round_trip_open_thread() -> None:
    original = DeepLink(action="open_thread", thread_id="my-thread", message="test msg")
    restored = DeepLink.parse(original.to_url())
    assert restored == original


def test_round_trip_open_thread_escapes_path_and_query_characters() -> None:
    original = DeepLink(action="open_thread", thread_id="thread/with slash", message="a/b&c=d")
    url = original.to_url()

    assert url == "nuself://thread/thread%2Fwith%20slash?message=a%2Fb%26c%3Dd"
    assert DeepLink.parse(url) == original


def test_round_trip_new_thread() -> None:
    original = DeepLink.for_new_thread(title="T", message="M", candidate_id="C")
    restored = DeepLink.parse(original.to_url())
    assert restored == original


def test_round_trip_new_thread_escapes_query_characters() -> None:
    original = DeepLink.for_new_thread(title="T/A", message="M&x=1", candidate_id="cand/1")
    restored = DeepLink.parse(original.to_url())

    assert restored == original


def test_invalid_scheme_raises() -> None:
    with pytest.raises(ValueError, match="unsupported deep link scheme"):
        DeepLink.parse("http://thread/default")


def test_invalid_path_raises() -> None:
    with pytest.raises(ValueError, match="unsupported deep link path"):
        DeepLink.parse("nuself://unknown/path")


def test_open_thread_missing_id_raises() -> None:
    with pytest.raises(ValueError, match="missing thread id"):
        DeepLink.parse("nuself://thread/")
