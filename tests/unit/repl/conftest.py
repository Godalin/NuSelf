from pathlib import Path

import pytest

from nuself.application.runtime import open_application_runtime, use_application_runtime


@pytest.fixture(autouse=True)
def application_runtime(tmp_path: Path):
    runtime = open_application_runtime(tmp_path)
    try:
        with use_application_runtime(runtime):
            yield
    finally:
        runtime.close()
