from nuself.cli.repl.registry import (
    command_body,
    command_names,
    command_tokens,
    render_help_lines,
    resolve_command,
    tokens_for,
)


def test_registry_drives_canonical_and_alias_matching() -> None:
    assert tokens_for("mem") == (":mem", ":m")
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


def test_registry_resolves_alias_to_canonical_name_and_body() -> None:
    resolved = resolve_command(":m search durable context")

    assert resolved is not None
    assert resolved.name == "mem"
    assert resolved.body == "search durable context"
    assert resolve_command(":memory search durable context") is None
    assert "mem" in command_names()


def test_reflection_is_an_independent_repl_command() -> None:
    resolved = resolve_command(":reflection status")

    assert resolved is not None
    assert resolved.name == "reflection"
    assert resolved.body == "status"
