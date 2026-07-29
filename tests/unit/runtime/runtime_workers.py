import threading

from nuself.runtime.workers import OwnedWorker


def test_owned_worker_start_is_duplicate_safe() -> None:
    release = threading.Event()
    calls: list[str] = []

    def target() -> None:
        calls.append("run")
        release.wait()

    worker = OwnedWorker(
        name="test",
        thread_name="test-worker",
        target=target,
    )

    assert worker.start() is True
    assert worker.start() is False
    release.set()
    snapshot = worker.join(timeout=1)

    assert calls == ["run"]
    assert snapshot.state == "stopped"
    assert snapshot.alive is False
    assert worker.start() is False


def test_owned_worker_join_timeout_remains_observable_until_exit() -> None:
    release = threading.Event()

    def target() -> None:
        release.wait()

    worker = OwnedWorker(
        name="test",
        thread_name="test-worker",
        target=target,
    )
    worker.start()

    timed_out = worker.join(timeout=0)

    assert timed_out.state == "timed_out"
    assert timed_out.alive is True
    release.set()
    stopped = worker.join(timeout=1)
    assert stopped.state == "stopped"
    assert stopped.alive is False
