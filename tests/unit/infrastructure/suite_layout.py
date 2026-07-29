from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = PROJECT_ROOT / "tests"


def test_default_collection_is_limited_to_unit_tree() -> None:
    configuration = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    pytest_options = configuration["tool"]["pytest"]["ini_options"]

    assert pytest_options["testpaths"] == ["tests/unit"]
    assert pytest_options["python_files"] == ["*.py"]


def test_test_modules_omit_redundant_prefix() -> None:
    modules = (
        path
        for root in (TEST_ROOT / "unit", TEST_ROOT / "live")
        for path in root.rglob("*.py")
        if path.name not in {"__init__.py", "conftest.py"}
    )

    assert not [
        path.relative_to(PROJECT_ROOT)
        for path in modules
        if path.name.startswith("test_")
    ]


def test_live_suite_keeps_explicit_opt_in_gate() -> None:
    live_conftest = (TEST_ROOT / "live" / "conftest.py").read_text(
        encoding="utf-8"
    )

    assert '"--run-live-api"' in live_conftest
    assert "default=False" in live_conftest
    assert "pytest.skip(" in live_conftest
