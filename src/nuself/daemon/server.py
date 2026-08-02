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
from nuself.daemon.operations_audit import (
    report_shutdown_cleanup_failure,
)
from nuself.daemon.signals import DaemonSignalOwner
from nuself.daemon.socket_server import (
    NuSelfUnixServer,
    RequestHandler,
)
from nuself.daemon.state import DaemonState
from nuself.runtime.cleanup import CleanupFailure, run_cleanup_steps
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.scope import NuSelfScope, resolve_scope
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


class DaemonRuntimeRecoveryError(RuntimeError):
    """Raised when stale runtime metadata cannot be fully reconciled."""

    def __init__(self, failures: tuple[CleanupFailure, ...]) -> None:
        super().__init__(
            f"daemon runtime metadata recovery failed in "
            f"{len(failures)} step(s)"
        )
        self.failures = failures


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
        report_shutdown_cleanup_failure(
            lifecycle_error,
            project_root=project_root,
            failures=cleanup_failures,
            primary_failed=primary_error is not None,
        )
        if primary_error is not None:
            raise lifecycle_error from primary_error
        raise lifecycle_error
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)


def run_daemon(authority: NuSelfScope | Path | None = None) -> int:
    """Run the local daemon until a shutdown request is received."""

    paths = runtime_paths(authority)
    ensure_runtime_dirs(paths)
    instance_lock = DaemonInstanceLock(paths.daemon_lock_path)
    try:
        instance_lock.acquire()
    except DaemonInstanceLockContended as exc:
        write_lifecycle_audit(
            "instance_lock_contended",
            project_root=paths.authority_root,
            error=diagnostic_exception_message(exc),
        )
        return 1
    primary_error: BaseException | None = None
    try:
        _run_owned_daemon(paths)
    except BaseException as exc:
        primary_error = exc
    cleanup_failures = run_cleanup_steps(
        (("instance_lock.release", instance_lock.release),)
    )
    _finish_daemon_lifecycle(
        project_root=paths.authority_root,
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
    )
    return 0


def _run_owned_daemon(paths: RuntimePaths) -> None:
    """Run the daemon while the caller holds project instance ownership."""

    state: DaemonState | None = None
    from nuself.application.runtime import (
        open_application_runtime,
        use_application_runtime,
    )

    application_runtime = open_application_runtime(paths.scope)
    signal_owner: DaemonSignalOwner | None = None
    ready = False
    primary_error: BaseException | None = None
    try:
        _reconcile_stale_runtime_metadata(paths)
        with use_application_runtime(application_runtime):
            state = DaemonState(application_runtime.application)
        signal_owner = DaemonSignalOwner(state.shutdown_requested)
        signal_owner.install()

        with NuSelfUnixServer(
            str(paths.socket_path),
            RequestHandler,
            state,
        ) as server:
            write_text_atomic(paths.pid_path, f"{os.getpid()}\n")
            state.start_background_tasks()
            if state.shutdown_requested.is_set():
                raise RuntimeError(
                    "daemon shutdown was requested before readiness"
                )
            if not state.scheduler.snapshot().running:
                raise RuntimeError("daemon scheduler is not running")
            write_lifecycle_audit(
                "started",
                project_root=paths.authority_root,
            )
            ready = True
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
                ("scheduler.stop", state.scheduler.shutdown),
            )
        )
    if signal_owner is not None:
        cleanup_steps.append(
            ("signal_handlers.restore", signal_owner.restore)
        )
    cleanup_steps.extend(
        (
            (
                "application_runtime.close",
                application_runtime.close,
            ),
            ("socket.unlink", lambda: paths.socket_path.unlink(missing_ok=True)),
            ("pid.unlink", lambda: paths.pid_path.unlink(missing_ok=True)),
        )
    )
    cleanup_failures = run_cleanup_steps(cleanup_steps)
    if ready and not cleanup_failures:
        write_lifecycle_audit(
            "stopped",
            project_root=paths.authority_root,
        )
    _finish_daemon_lifecycle(
        project_root=paths.authority_root,
        primary_error=primary_error,
        cleanup_failures=cleanup_failures,
    )


def _reconcile_stale_runtime_metadata(paths: RuntimePaths) -> None:
    recovered: dict[str, object] = {
        "socket": False,
        "pid": False,
    }

    def remove_stale(name: str, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        recovered[name] = True

    failures = run_cleanup_steps(
        (
            (
                "stale_socket.unlink",
                lambda: remove_stale("socket", paths.socket_path),
            ),
            (
                "stale_pid.unlink",
                lambda: remove_stale("pid", paths.pid_path),
            ),
        )
    )
    if failures:
        raise DaemonRuntimeRecoveryError(failures) from failures[0].error
    if any(recovered.values()):
        write_lifecycle_audit(
            "runtime_metadata_recovered",
            project_root=paths.authority_root,
            metadata=recovered,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nuself.daemon.server")
    parser.add_argument("--user-root", type=Path, default=None)
    parser.add_argument("--workspace-root", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.user_root is None:
        if args.workspace_root is not None:
            parser.error("--workspace-root requires --user-root")
        scope = resolve_scope()
    else:
        scope = resolve_scope(
            workspace=args.workspace_root,
            environ={"NUSELF_HOME": str(args.user_root)},
        )
    return run_daemon(scope)


if __name__ == "__main__":
    raise SystemExit(main())
