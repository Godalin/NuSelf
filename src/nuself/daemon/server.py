"""Local Unix-socket daemon server."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path

from nuself.config import (
    RuntimePaths,
    ensure_runtime_dirs,
    runtime_paths,
)
from nuself.daemon.audit import write_lifecycle_audit
from nuself.daemon.instance import (
    DaemonInstanceLock,
    DaemonInstanceLockContended,
)
from nuself.daemon.signals import DaemonSignalOwner
from nuself.daemon.socket_server import (
    NuSelfUnixServer,
    RequestHandler,
)
from nuself.daemon.state import DaemonState
from nuself.runtime.cleanup import CleanupFailure, run_cleanup_steps
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.observability import report_observed_failure
from nuself.storage import write_text_atomic


class DaemonLifecycleError(RuntimeError):
    """Raised after daemon lifecycle cleanup retains one or more failures."""

    def __init__(
        self,
        failures: tuple[CleanupFailure, ...],
        *,
        primary_error: BaseException | None = None,
    ) -> None:
        super().__init__(
            f"daemon lifecycle cleanup failed in {len(failures)} step(s)"
        )
        self.failures = failures
        self.primary_error = primary_error


def _finish_daemon_lifecycle(
    *,
    project_root: Path,
    primary_error: BaseException | None,
    cleanup_failures: tuple[CleanupFailure, ...],
) -> None:
    if cleanup_failures:
        lifecycle_error = DaemonLifecycleError(
            cleanup_failures,
            primary_error=primary_error,
        )
        report_observed_failure(
            lifecycle_error,
            component="daemon",
            event="shutdown_cleanup_failed",
            message="Daemon lifecycle cleanup failed",
            project_root=project_root,
            metadata={
                "steps": [failure.step for failure in cleanup_failures],
                "primary_failed": primary_error is not None,
            },
            level="error",
            status="error",
        )
        if primary_error is not None:
            raise lifecycle_error from primary_error
        raise lifecycle_error
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)


def run_daemon(project_root: Path | None = None) -> int:
    """Run the local daemon until a shutdown request is received."""

    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    instance_lock = DaemonInstanceLock(
        paths.runtime_dir / "nuself.lock"
    )
    try:
        instance_lock.acquire()
    except DaemonInstanceLockContended as exc:
        write_lifecycle_audit(
            "instance_lock_contended",
            "daemon start rejected because this project already has an owner",
            project_root=paths.project_root,
            level="warning",
            status="skipped",
            error=diagnostic_exception_message(exc),
        )
        return 1
    result = 0
    primary_error: BaseException | None = None
    try:
        result = _run_owned_daemon(paths)
    except BaseException as exc:
        primary_error = exc
    cleanup_failures = run_cleanup_steps(
        (("instance_lock.release", instance_lock.release),)
    )
    _finish_daemon_lifecycle(
        project_root=paths.project_root,
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
    )
    return result


def _run_owned_daemon(paths: RuntimePaths) -> int:
    """Run the daemon while the caller holds project instance ownership."""

    state: DaemonState | None = None
    signal_owner: DaemonSignalOwner | None = None
    started = False
    primary_error: BaseException | None = None
    try:
        paths.socket_path.unlink(missing_ok=True)
        write_text_atomic(paths.pid_path, f"{os.getpid()}\n")
        state = DaemonState(paths.project_root)
        signal_owner = DaemonSignalOwner(state.shutdown_requested)
        signal_owner.install()

        with NuSelfUnixServer(
            str(paths.socket_path),
            RequestHandler,
            state,
        ) as server:
            write_lifecycle_audit(
                "started",
                "daemon started",
                project_root=paths.project_root,
            )
            started = True
            state.start_background_memory_curator()
            state.start_background_reflection_scheduler()
            state.start_background_reason_scheduler()
            state.start_background_export_worker()
            state.start_background_notification_delivery()
            server.timeout = 0.2
            while not state.shutdown_requested.is_set():
                server.handle_request()
    except BaseException as exc:
        primary_error = exc

    cleanup_steps: list[tuple[str, Callable[[], object]]] = []
    if state is not None:
        cleanup_steps.extend(
            (
                ("shutdown.signal", state.shutdown_requested.set),
                (
                    "worker.memory_curator.stop",
                    state.stop_background_memory_curator,
                ),
                (
                    "worker.reflection_scheduler.stop",
                    state.stop_background_reflection_scheduler,
                ),
                (
                    "worker.reason_scheduler.stop",
                    state.stop_background_reason_scheduler,
                ),
                (
                    "worker.export_worker.stop",
                    state.stop_background_export_worker,
                ),
                (
                    "worker.notification_delivery.stop",
                    state.stop_background_notification_delivery,
                ),
            )
        )
    if signal_owner is not None:
        cleanup_steps.append(
            ("signal_handlers.restore", signal_owner.restore)
        )
    from nuself.storage import reset_default_backend

    cleanup_steps.extend(
        (
            (
                "storage.default_backend.reset",
                lambda: reset_default_backend(paths.project_root),
            ),
            ("socket.unlink", lambda: paths.socket_path.unlink(missing_ok=True)),
            ("pid.unlink", lambda: paths.pid_path.unlink(missing_ok=True)),
        )
    )
    cleanup_failures = run_cleanup_steps(cleanup_steps)
    if started and not cleanup_failures:
        write_lifecycle_audit(
            "stopped",
            "daemon stopped",
            project_root=paths.project_root,
        )
    _finish_daemon_lifecycle(
        project_root=paths.project_root,
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nuself.daemon.server")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args(argv)
    return run_daemon(args.project_root)


if __name__ == "__main__":
    raise SystemExit(main())
