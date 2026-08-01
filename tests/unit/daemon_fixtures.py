"""Explicit daemon application ownership for adapter tests."""

from pathlib import Path

from nuself.application.runtime import ApplicationRuntime, open_application_runtime
from nuself.daemon.state import DaemonState


class DaemonStateOwner:
    def __init__(self) -> None:
        self._states: list[DaemonState] = []
        self._runtimes: list[ApplicationRuntime] = []

    def create(self, project_root: Path, *, start: bool = False) -> DaemonState:
        runtime = open_application_runtime(project_root)
        state = DaemonState(runtime.application)
        if start:
            state.scheduler.start()
        self._runtimes.append(runtime)
        self._states.append(state)
        return state

    def close(self) -> None:
        while self._states:
            self._states.pop().scheduler.shutdown()
        while self._runtimes:
            self._runtimes.pop().close()
