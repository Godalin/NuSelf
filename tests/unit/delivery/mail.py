"""Email notification rendering tests."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from nuself.config.settings import EmailConfig
from nuself.delivery.email import _build_email_message
from nuself.inbox.model import InboxItem


def test_html_email_preserves_trace_line_boundaries() -> None:
    body = (
        "Reflection <body>.\n\n"
        "Provenance chain:\n"
        "memory:m1  Test belief: bounded excerpt.\n"
        "decision:relevance  Relevance gate passed."
    )
    message = _build_email_message(
        InboxItem(
            id="inbox-reflection-1",
            kind="reflection",
            source_id="reflection-1",
            title="New reflection: Test",
            body=body,
            idempotency_key="reflection-1",
            deep_link="nuself://conversation/default",
        ),
        EmailConfig(
            from_address="nuself@example.test",
            to_address="user@example.test",
        ),
    )

    plain = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    assert plain is not None
    assert html is not None
    assert plain.get_content().rstrip() == body
    html_body = html.get_content()
    assert "Reflection &lt;body&gt;.<br>" in html_body
    assert "&nbsp;<br>" in html_body
    assert "Provenance chain:<br>" in html_body
    assert "memory:m1  Test belief: bounded excerpt.<br>" in html_body
    assert "decision:relevance  Relevance gate passed." in html_body
