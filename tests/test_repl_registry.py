from nuself.cli.repl.registry import (
    command_body,
    command_matches,
    command_tokens,
    render_help_lines,
    tokens_for,
)


def test_registry_drives_canonical_and_alias_matching() -> None:
    assert tokens_for("mem") == (":mem", ":m")
    assert command_matches(":m", "mem")
    assert command_body(":mem search durable context", "mem") == (
        "search durable context"
    )
    assert command_body(":memory", "mem") is None


def test_registry_drives_completion_tokens_and_help() -> None:
    tokens = command_tokens()
    help_text = "\n".join(render_help_lines())

    assert len(tokens) == len(set(tokens))
    assert {":q", ":quit", ":exit", ":persona", ":p"} <= set(tokens)
    assert ":mem, :m                  preview memory entries" in help_text
