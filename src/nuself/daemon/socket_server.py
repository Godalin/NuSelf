"""Unix-socket transport adapter for typed daemon requests."""

from __future__ import annotations

import socketserver
from pathlib import Path
from typing import override

from nuself.daemon.protocol import (
    DaemonPeerDisconnected,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
)
from nuself.daemon.request_handlers import (
    DaemonRequestState,
    handle_request,
)
from nuself.daemon.transport import (
    read_socket_frame,
    write_stream_frame,
)
from nuself.daemon.transport_audit import (
    report_daemon_transport_failure,
)

DAEMON_REQUEST_IO_TIMEOUT_SECONDS = 5.0


class NuSelfUnixServer(socketserver.ThreadingUnixStreamServer):
    """Unix stream server carrying structural daemon request state."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        socket_path: str,
        handler: type[socketserver.BaseRequestHandler],
        state: DaemonRequestState,
    ) -> None:
        self.state = state
        super().__init__(socket_path, handler)


class RequestHandler(socketserver.StreamRequestHandler):
    """Handle one bounded JSONL request per client connection."""

    @override
    def handle(self) -> None:
        request_id: str | None = None
        try:
            self.connection.settimeout(
                DAEMON_REQUEST_IO_TIMEOUT_SECONDS
            )
            raw_line = read_socket_frame(self.connection)
        except DaemonPeerDisconnected:
            return
        except ProtocolError as exc:
            response = DaemonResponse.fail_from_exception("unknown", exc)
        except OSError as exc:
            report_daemon_transport_failure(
                exc,
                event="request_transport_failed",
                project_root=self._request_project_root(),
                request_id=None,
            )
            response = DaemonResponse.fail_from_exception(
                "unknown",
                exc,
                include_chain=True,
            )
        else:
            try:
                request = DaemonRequest.from_json_line(raw_line)
            except ProtocolError as exc:
                response = DaemonResponse.fail_from_exception(
                    "unknown",
                    exc,
                )
            else:
                request_id = request.request_id
                try:
                    server = self.server
                    if not isinstance(server, NuSelfUnixServer):
                        raise RuntimeError("unexpected server type")
                    response = handle_request(
                        request,
                        server.state,
                    )
                except Exception as exc:
                    report_daemon_transport_failure(
                        exc,
                        event="request_failed",
                        project_root=self._request_project_root(),
                        request_id=request_id,
                    )
                    response = DaemonResponse.fail_from_exception(
                        request_id,
                        exc,
                        include_chain=True,
                    )

        fallback = False
        try:
            frame = response.to_json_line()
        except ProtocolError as exc:
            report_daemon_transport_failure(
                exc,
                event="response_encode_failed",
                project_root=self._request_project_root(),
                request_id=request_id,
                metadata={"response_status": response.status},
            )
            response = DaemonResponse.fail(
                request_id or "unknown",
                "daemon response encoding failed",
            )
            frame = response.to_json_line()
            fallback = True

        try:
            write_stream_frame(self.wfile, frame)
        except OSError as exc:
            report_daemon_transport_failure(
                exc,
                event="response_delivery_failed",
                project_root=self._request_project_root(),
                request_id=request_id,
                metadata={
                    "response_status": response.status,
                    "fallback": fallback,
                },
            )

    def _request_project_root(self) -> Path | None:
        server = self.server
        if not isinstance(server, NuSelfUnixServer):
            return None
        return server.state.project_root
