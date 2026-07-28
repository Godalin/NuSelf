from __future__ import annotations

from nuself.runtime.cleanup import run_cleanup_steps


def test_cleanup_runner_attempts_all_steps_and_retains_base_failures() -> None:
    calls: list[str] = []
    ordinary = ValueError("ordinary failure")
    interrupt = KeyboardInterrupt("interrupted cleanup")
    exit_error = SystemExit(7)

    def succeed() -> None:
        calls.append("succeed")

    def fail(
        step: str,
        error: BaseException,
    ) -> None:
        calls.append(step)
        raise error

    failures = run_cleanup_steps(
        (
            ("ordinary", lambda: fail("ordinary", ordinary)),
            ("interrupt", lambda: fail("interrupt", interrupt)),
            ("exit", lambda: fail("exit", exit_error)),
            ("succeed", succeed),
        )
    )

    assert calls == ["ordinary", "interrupt", "exit", "succeed"]
    assert [failure.step for failure in failures] == [
        "ordinary",
        "interrupt",
        "exit",
    ]
    assert [failure.error for failure in failures] == [
        ordinary,
        interrupt,
        exit_error,
    ]
