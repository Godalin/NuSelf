"""Deep link parsing and resolution for notification outbox entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse


@dataclass(frozen=True)
class DeepLink:
    """Parsed NuSelf deep link."""

    action: Literal["open_conversation", "new_conversation"]
    conversation_id: str | None = None
    title: str | None = None
    message: str | None = None
    candidate_id: str | None = None

    @classmethod
    def parse(cls, url: str) -> "DeepLink":
        """Parse a deep link URL.

        Supported formats::

            nuself://conversation/<conversation-id>?message=<optional-message>
            nuself://new-conversation?title=...&message=...&candidate_id=...
        """
        parsed = urlparse(url)
        if parsed.scheme != "nuself":
            raise ValueError(f"unsupported deep link scheme: {parsed.scheme}")
        if parsed.fragment:
            raise ValueError("deep link fragments are not supported")
        # urlparse may put the first path segment in netloc for non-standard schemes
        path = parsed.path
        if parsed.netloc:
            path = "/" + parsed.netloc + path

        if path.startswith("/conversation/"):
            conversation_id = unquote(path[len("/conversation/") :])
            if not conversation_id:
                raise ValueError("deep link missing conversation id")
            query = parse_qs(parsed.query)
            message = query.get("message", [None])[0]
            return cls(action="open_conversation", conversation_id=conversation_id, message=message)

        if path == "/new-conversation" or parsed.netloc == "new-conversation":
            query = parse_qs(parsed.query)
            title = query.get("title", [None])[0]
            message = query.get("message", [None])[0]
            candidate_id = query.get("candidate_id", [None])[0]
            return cls(action="new_conversation", title=title, message=message, candidate_id=candidate_id)

        raise ValueError(f"unsupported deep link path: {path}")

    def to_url(self) -> str:
        """Serialize back to URL string."""
        if self.action == "open_conversation":
            if self.conversation_id is None:
                raise ValueError("open_conversation deep link requires conversation_id")
            conversation_id = quote(self.conversation_id, safe="")
            if self.message is not None:
                return f"nuself://conversation/{conversation_id}?{_encode_query({'message': self.message})}"
            return f"nuself://conversation/{conversation_id}"

        if self.action == "new_conversation":
            params: dict[str, str] = {}
            if self.title is not None:
                params["title"] = self.title
            if self.message is not None:
                params["message"] = self.message
            if self.candidate_id is not None:
                params["candidate_id"] = self.candidate_id
            if params:
                return "nuself://new-conversation?" + _encode_query(params)
            return "nuself://new-conversation"

        raise ValueError(f"unsupported deep link action: {self.action}")

    @classmethod
    def for_new_conversation(
        cls,
        title: str | None = None,
        message: str | None = None,
        candidate_id: str | None = None,
    ) -> "DeepLink":
        """Create a deep link that opens a new conversation."""
        return cls(action="new_conversation", title=title, message=message, candidate_id=candidate_id)


def _encode_query(params: dict[str, str]) -> str:
    return urlencode(params, quote_via=quote)
