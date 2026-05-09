"""Deep link parsing and resolution for notification outbox entries."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class DeepLink:
    """Parsed NuSelf deep link."""

    thread_id: str
    message: str | None = None

    @classmethod
    def parse(cls, url: str) -> "DeepLink":
        """Parse a deep link URL.

        Supported format::

            nuself://thread/<thread-id>?message=<optional-message>
        """
        parsed = urlparse(url)
        if parsed.scheme != "nuself":
            raise ValueError(f"unsupported deep link scheme: {parsed.scheme}")
        # urlparse may put the first path segment in netloc for non-standard schemes
        path = parsed.path
        if parsed.netloc:
            path = "/" + parsed.netloc + path
        if not path.startswith("/thread/"):
            raise ValueError(f"unsupported deep link path: {path}")
        thread_id = path[len("/thread/") :]
        if not thread_id:
            raise ValueError("deep link missing thread id")
        query = parse_qs(parsed.query)
        message = query.get("message", [None])[0]
        return cls(thread_id=thread_id, message=message)

    def to_url(self) -> str:
        """Serialize back to URL string."""
        if self.message is not None:
            from urllib.parse import quote

            return f"nuself://thread/{self.thread_id}?message={quote(self.message)}"
        return f"nuself://thread/{self.thread_id}"
