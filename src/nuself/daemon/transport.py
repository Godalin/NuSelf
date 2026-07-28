"""Bounded one-frame IO for the local daemon JSONL transport."""

from __future__ import annotations

from typing import Protocol

from nuself.daemon.protocol import (
    MAX_DAEMON_FRAME_BYTES,
    DaemonExtraFrameData,
    DaemonFrameTooLarge,
    DaemonIncompleteFrame,
    DaemonPeerDisconnected,
)

_SOCKET_CHUNK_BYTES = 4096


class BinaryFrameReader(Protocol):
    def readline(self, size: int | None = -1, /) -> bytes: ...


class BinaryFrameWriter(Protocol):
    def write(self, data: bytes, /) -> int | None: ...
    def flush(self) -> None: ...


class SocketFrameReader(Protocol):
    def recv(self, size: int, /) -> bytes: ...


def read_stream_frame(stream: BinaryFrameReader) -> bytes:
    """Read one bounded newline-terminated frame from a buffered stream."""

    frame = stream.readline(MAX_DAEMON_FRAME_BYTES + 1)
    if not frame:
        raise DaemonPeerDisconnected(
            "peer closed connection before sending a frame"
        )
    if len(frame) > MAX_DAEMON_FRAME_BYTES:
        raise DaemonFrameTooLarge(
            f"daemon frame exceeds {MAX_DAEMON_FRAME_BYTES} bytes"
        )
    if not frame.endswith(b"\n"):
        if len(frame) >= MAX_DAEMON_FRAME_BYTES:
            raise DaemonFrameTooLarge(
                f"daemon frame exceeds {MAX_DAEMON_FRAME_BYTES} bytes"
            )
        raise DaemonIncompleteFrame(
            "daemon frame ended before its newline"
        )
    return frame


def read_socket_frame(sock: SocketFrameReader) -> bytes:
    """Receive one bounded frame, rejecting received trailing frame bytes."""

    buffer = bytearray()
    while True:
        chunk = sock.recv(_SOCKET_CHUNK_BYTES)
        if not chunk:
            if not buffer:
                raise DaemonPeerDisconnected(
                    "peer closed connection before sending a frame"
                )
            raise DaemonIncompleteFrame(
                "daemon frame ended before its newline"
            )
        newline = chunk.find(b"\n")
        if newline >= 0:
            buffer.extend(chunk[: newline + 1])
            if len(buffer) > MAX_DAEMON_FRAME_BYTES:
                raise DaemonFrameTooLarge(
                    f"daemon frame exceeds {MAX_DAEMON_FRAME_BYTES} bytes"
                )
            if chunk[newline + 1 :]:
                raise DaemonExtraFrameData(
                    "daemon connection contains more than one frame"
                )
            return bytes(buffer)
        buffer.extend(chunk)
        if len(buffer) >= MAX_DAEMON_FRAME_BYTES:
            raise DaemonFrameTooLarge(
                f"daemon frame exceeds {MAX_DAEMON_FRAME_BYTES} bytes"
            )


def write_stream_frame(stream: BinaryFrameWriter, frame: bytes) -> None:
    """Write and flush one complete frame, handling partial stream writes."""

    offset = 0
    while offset < len(frame):
        written = stream.write(frame[offset:])
        if written is None or written <= 0:
            raise OSError("daemon response stream made no write progress")
        offset += written
    stream.flush()
