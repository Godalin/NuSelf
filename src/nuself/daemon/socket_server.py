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
from nuself.runtime.context import runtime_context
from nuself.runtime.observability import (
    format_exception_chain,
    report_observed_failure,
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
        request_id = "unknown"
        try:
            self.connection.settimeout(
                DAEMON_REQUEST_IO_TIMEOUT_SECONDS
            )
            raw_line = read_socket_frame(self.connection)
        except DaemonPeerDisconnected:
            return
        except ProtocolError as exc:
            response = DaemonResponse.fail(request_id, str(exc))
        except OSError as exc:
            report_observed_failure(
                exc,
                component="daemon",
                event="request_transport_failed",
                message="Daemon request transport failed",
                project_root=self._request_project_root(),
                metadata=None,
                level="warning",
                status="error",
            )
            response = DaemonResponse.fail(
                request_id,
                format_exception_chain(exc),
            )
        else:
            try:
                request = DaemonRequest.from_json_line(raw_line)
                request_id = request.request_id
                response = handle_request(request, self._daemon_state())
            except ProtocolError as exc:
                response = DaemonResponse.fail(request_id, str(exc))
            except Exception as exc:
                chain = format_exception_chain(exc)
                with runtime_context(
                    request_id=request_id,
                    source="daemon",
                ):
                    report_observed_failure(
                        exc,
                        component="daemon",
                        event="request_failed",
                        message="Daemon request handling failed",
                        project_root=self._request_project_root(),
                        metadata=None,
                        level="error",
                        status="error",
                    )
                response = DaemonResponse.fail(request_id, chain)

        try:
            write_stream_frame(self.wfile, response.to_json_line())
        except (OSError, ProtocolError) as exc:
            context = (
                runtime_context(
                    request_id=request_id,
                    source="daemon",
                )
                if request_id != "unknown"
                else runtime_context(source="daemon")
            )
            with context:
                report_observed_failure(
                    exc,
                    component="daemon",
                    event="response_delivery_failed",
                    message="Daemon response could not be delivered",
                    project_root=self._request_project_root(),
                    metadata=None,
                    level="warning",
                    status="error",
                )

    def _request_project_root(self) -> Path | None:
        try:
            return self._daemon_state().project_root
        except Exception:
            return None

    def _daemon_state(self) -> DaemonRequestState:
        server = self.server
        if not isinstance(server, NuSelfUnixServer):
            raise RuntimeError("unexpected server type")
        return server.state
