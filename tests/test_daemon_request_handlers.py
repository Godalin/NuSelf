from nuself.daemon.protocol import REQUEST_TYPES
from nuself.daemon.request_handlers import (
    DAEMON_REQUEST_HANDLERS,
    build_daemon_request_registry,
)


def test_daemon_request_registry_is_complete_and_sealed() -> None:
    assert DAEMON_REQUEST_HANDLERS.sealed
    assert set(DAEMON_REQUEST_HANDLERS.registered_keys) == set(
        REQUEST_TYPES
    )


def test_daemon_request_registry_builder_isolated() -> None:
    rebuilt = build_daemon_request_registry()

    assert rebuilt is not DAEMON_REQUEST_HANDLERS
    assert rebuilt.sealed
