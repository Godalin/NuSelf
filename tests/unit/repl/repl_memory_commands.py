from pathlib import Path

import pytest

from nuself.cli.repl.commands import handle_interactive_memory_command


@pytest.mark.parametrize(
    ("command", "label"),
    (
        ("show 0", "memory"),
        ("review 0", "memory candidate"),
        ("source 0", "source document"),
    ),
)
def test_numeric_memory_handles_use_shared_index_validation(
    tmp_path: Path,
    command: str,
    label: str,
) -> None:
    assert handle_interactive_memory_command(command, tmp_path) == (
        f"Invalid {label} index 0. Valid range: (none)"
    )
