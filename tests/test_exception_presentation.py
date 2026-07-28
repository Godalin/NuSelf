from __future__ import annotations

import ast
from pathlib import Path


def test_codebase_does_not_render_caught_exceptions_directly() -> None:
    source_root = Path(__file__).parents[1] / "src" / "nuself"
    violations: list[str] = []

    for path in source_root.rglob("*.py"):
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        for handler in (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and isinstance(node.name, str)
        ):
            for node in ast.walk(handler):
                if (
                    isinstance(node, ast.FormattedValue)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == handler.name
                ):
                    violations.append(
                        f"{path.relative_to(source_root)}:{node.lineno}"
                    )
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "str"
                    and len(node.args) == 1
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == handler.name
                ):
                    violations.append(
                        f"{path.relative_to(source_root)}:{node.lineno}"
                    )

    assert violations == []
