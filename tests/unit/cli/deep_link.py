"""Tests for DeepLink parsing and serialization."""

from __future__ import annotations

import pytest

from nuself.notification.deep_link import DeepLink


def test_parse_open_conversation() -> None:
    link = DeepLink.parse("nuself://conversation/default")
    assert link.action == "open_conversation"
    assert link.conversation_id == "default"
    assert link.message is None


def test_parse_open_conversation_with_message() -> None:
    link = DeepLink.parse("nuself://conversation/default?message=hello%20world")
    assert link.action == "open_conversation"
    assert link.conversation_id == "default"
    assert link.message == "hello world"


def test_parse_new_conversation() -> None:
    link = DeepLink.parse("nuself://new-conversation?title=My%20Conversation&message=hello&candidate_id=c1")
    assert link.action == "new_conversation"
    assert link.title == "My Conversation"
    assert link.message == "hello"
    assert link.candidate_id == "c1"


def test_parse_new_conversation_minimal() -> None:
    link = DeepLink.parse("nuself://new-conversation")
    assert link.action == "new_conversation"
    assert link.title is None
    assert link.message is None
    assert link.candidate_id is None


def test_to_url_open_conversation() -> None:
    link = DeepLink(action="open_conversation", conversation_id="default")
    assert link.to_url() == "nuself://conversation/default"


def test_to_url_open_conversation_with_message() -> None:
    link = DeepLink(action="open_conversation", conversation_id="default", message="hello world")
    assert link.to_url() == "nuself://conversation/default?message=hello%20world"


def test_to_url_new_conversation() -> None:
    link = DeepLink.for_new_conversation(title="My Conversation", message="hello", candidate_id="c1")
    url = link.to_url()
    assert url.startswith("nuself://new-conversation?")
    assert "title=My%20Conversation" in url
    assert "message=hello" in url
    assert "candidate_id=c1" in url


def test_to_url_new_conversation_minimal() -> None:
    link = DeepLink.for_new_conversation()
    assert link.to_url() == "nuself://new-conversation"


def test_round_trip_open_conversation() -> None:
    original = DeepLink(action="open_conversation", conversation_id="my-conversation", message="test msg")
    restored = DeepLink.parse(original.to_url())
    assert restored == original


def test_round_trip_open_conversation_escapes_path_and_query_characters() -> None:
    original = DeepLink(action="open_conversation", conversation_id="conversation/with slash", message="a/b&c=d")
    url = original.to_url()

    assert url == "nuself://conversation/conversation%2Fwith%20slash?message=a%2Fb%26c%3Dd"
    assert DeepLink.parse(url) == original


def test_round_trip_new_conversation() -> None:
    original = DeepLink.for_new_conversation(title="T", message="M", candidate_id="C")
    restored = DeepLink.parse(original.to_url())
    assert restored == original


def test_round_trip_new_conversation_escapes_query_characters() -> None:
    original = DeepLink.for_new_conversation(title="T/A", message="M&x=1", candidate_id="cand/1")
    restored = DeepLink.parse(original.to_url())

    assert restored == original


def test_invalid_scheme_raises() -> None:
    with pytest.raises(ValueError, match="unsupported deep link scheme"):
        DeepLink.parse("http://conversation/default")


def test_invalid_path_raises() -> None:
    with pytest.raises(ValueError, match="unsupported deep link path"):
        DeepLink.parse("nuself://unknown/path")


def test_open_conversation_missing_id_raises() -> None:
    with pytest.raises(ValueError, match="missing conversation id"):
        DeepLink.parse("nuself://conversation/")
