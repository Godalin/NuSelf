from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from types import FrameType

import pytest

from nuself.daemon.signals import (
    DaemonSignalInstallCleanupError,
    DaemonSignalOwner,
    DaemonSignalRestoreError,
)

SignalHandler = int | Callable[[int, FrameType | None], object]


def _handler(
    signal_number: int,
    frame: FrameType | None,
) -> None:
    del signal_number, frame


def test_signal_owner_sets_shutdown_and_restores_in_reverse_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutdown = threading.Event()
    owner = DaemonSignalOwner(shutdown)
    previous: dict[int, SignalHandler] = {
        signal.SIGINT: _handler,
        signal.SIGTERM: signal.Handlers.SIG_IGN,
    }
    current = dict(previous)
    writes: list[tuple[int, SignalHandler]] = []

    def get_signal(signal_number: int) -> SignalHandler:
        return current[signal_number]

    def set_signal(
        signal_number: int,
        handler: SignalHandler,
    ) -> SignalHandler:
        old = current[signal_number]
        current[signal_number] = handler
        writes.append((signal_number, handler))
        return old

    monkeypatch.setattr(signal, "getsignal", get_signal)
    monkeypatch.setattr(signal, "signal", set_signal)

    assert owner.install() is True
    assert owner.install() is False

    installed = current[signal.SIGINT]
    assert callable(installed)
    installed(signal.SIGINT, None)
    assert shutdown.is_set()

    assert owner.restore() is True
    assert owner.restore() is False
    assert current == previous
    assert [signal_number for signal_number, _ in writes[-2:]] == [
        signal.SIGTERM,
        signal.SIGINT,
    ]


def test_partial_install_rolls_back_successful_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = DaemonSignalOwner(threading.Event())
    previous: dict[int, SignalHandler] = {
        signal.SIGINT: signal.Handlers.SIG_DFL,
        signal.SIGTERM: signal.Handlers.SIG_IGN,
    }
    current = dict(previous)
    install_writes = 0

    def get_signal(signal_number: int) -> SignalHandler:
        return current[signal_number]

    def set_signal(
        signal_number: int,
        handler: SignalHandler,
    ) -> SignalHandler:
        nonlocal install_writes
        install_writes += 1
        if install_writes == 2:
            raise OSError("SIGTERM install failed")
        old = current[signal_number]
        current[signal_number] = handler
        return old

    monkeypatch.setattr(signal, "getsignal", get_signal)
    monkeypatch.setattr(signal, "signal", set_signal)

    with pytest.raises(OSError, match="SIGTERM install failed"):
        owner.install()

    assert current == previous
    assert owner.restore() is False


def test_partial_install_retains_failed_rollback_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = DaemonSignalOwner(threading.Event())
    previous: dict[int, SignalHandler] = {
        signal.SIGINT: signal.Handlers.SIG_DFL,
        signal.SIGTERM: signal.Handlers.SIG_IGN,
    }
    current = dict(previous)
    call_count = 0
    allow_restore = False

    def get_signal(signal_number: int) -> SignalHandler:
        return current[signal_number]

    def set_signal(
        signal_number: int,
        handler: SignalHandler,
    ) -> SignalHandler:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("SIGTERM install failed")
        if call_count == 3 and not allow_restore:
            raise OSError("SIGINT rollback failed")
        old = current[signal_number]
        current[signal_number] = handler
        return old

    monkeypatch.setattr(signal, "getsignal", get_signal)
    monkeypatch.setattr(signal, "signal", set_signal)

    with pytest.raises(
        DaemonSignalInstallCleanupError,
        match="rollback was incomplete",
    ) as captured:
        owner.install()

    assert isinstance(captured.value.__cause__, OSError)
    assert captured.value.failures[0].signal_number == signal.SIGINT

    allow_restore = True
    assert owner.restore() is True
    assert current == previous


def test_restore_attempts_all_signals_and_failed_one_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = DaemonSignalOwner(threading.Event())
    previous: dict[int, SignalHandler] = {
        signal.SIGINT: signal.Handlers.SIG_DFL,
        signal.SIGTERM: signal.Handlers.SIG_IGN,
    }
    current = dict(previous)
    restoring = False
    term_restore_fails = True

    def get_signal(signal_number: int) -> SignalHandler:
        return current[signal_number]

    def set_signal(
        signal_number: int,
        handler: SignalHandler,
    ) -> SignalHandler:
        if (
            restoring
            and signal_number == signal.SIGTERM
            and term_restore_fails
        ):
            raise OSError("SIGTERM restore failed")
        old = current[signal_number]
        current[signal_number] = handler
        return old

    monkeypatch.setattr(signal, "getsignal", get_signal)
    monkeypatch.setattr(signal, "signal", set_signal)
    owner.install()

    restoring = True
    with pytest.raises(DaemonSignalRestoreError) as captured:
        owner.restore()

    assert [item.signal_number for item in captured.value.failures] == [
        signal.SIGTERM
    ]
    assert current[signal.SIGINT] is previous[signal.SIGINT]

    term_restore_fails = False
    assert owner.restore() is True
    assert owner.restore() is False
    assert current == previous
