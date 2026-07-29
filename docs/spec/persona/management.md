# Persona Management Spec

Status: implemented current contract.

## Purpose

Provide a unified management interface (CLI + REPL + agent tools) for global
dynamic personas, using the same visible-index handle pattern as memory,
reflection, reason, and trace resources. This covers:

- **List** with `[0]`, `[1]` markers
- **Show** details
- **Delete** by handle
- **Disable / Enable** — new capability not present in V1
- **Filtering disabled personas** from activation and tool consumption

Built-in static personas remain hardcoded and are **not** deletable or
disableable through this interface. They appear in `persona list` for
information only (without handle markers).

## Core Principle

A global dynamic persona is either **active** (available for activation and
tool calls) or **disabled** (hidden from activation policy and `persona_list`,
rejected by `persona_think`). Disabling is reversible. Deleting removes the
persona permanently.

## Data Model

### PersonaPrompt (extended)

```python
@dataclass(frozen=True)
class PersonaPrompt:
    id: str             # uuid4 hex
    name: str           # human-readable label
    prompt: str         # the prompt text
    disabled: bool      # NEW — false by default
    created_at: str     # ISO timestamp
    updated_at: str     # ISO timestamp
```

- `disabled = True` means the persona exists but is **suspended**.
- `from_wire` defaults `disabled` to `False` for backward compatibility with
  existing persona files that lack the field.

### PersonaPromptRepository (extended)

The repository consumes one `StorageCollection` protocol. Global personas use
the durable `persona_prompts` collection; reason-thread personas use a
workspace-scoped collection adapter over `SqliteStore`. There is no raw
directory mode, JSON file scanner, or derived name index.

Method:

```python
def set_disabled(self, prompt_id: str, disabled: bool) -> None: ...
```

Implemented by reading the collection record, calling `with_updates(...)`, and
writing it back through the same collection.

## CLI

### Command Changes

Replace `name_or_id` positional argument with `<handle>` (visible index or
stable id) for `show`, `delete`, `enable`, `disable`.

```text
nuself persona list
  → Shows built-in static personas (info only, no markers)
  → Shows dynamic personas with [N] markers, disabled status, and (disabled) tag
nuself persona create <name> <prompt>   # NEW — create from one sentence
nuself persona show <handle>
nuself persona delete <handle> [--yes]
nuself persona disable <handle>         # NEW
nuself persona enable <handle>          # NEW
```

### `persona create`

```
nuself persona create rust-expert "你是一个Rust专家，擅长分析内存安全和并发问题"
```

CLI 版的 `persona_craft`。接收 `<name>`（40 字符以内）和 `<prompt>`（一句话描述），
调用 `create_persona_prompt()` 生成 `PersonaPrompt` 并保存，记录 trace。
与 `persona_craft` 工具相同：同名更新，创建新 id。

### REPL

```
:persona create <name> <prompt>        # NEW
```

### List Output Format

```
Built-in personas (static):
  analyst_self: Decomposes into concepts/assumptions
  ...

Custom personas (dynamic):
[0] rust-expert (id=abc123) [disabled]
[1] socratic-tutor (id=def456)
```

A disabled persona shows `[disabled]` after its name. The list includes
disabled personas so users can re-enable them.

### Handle Resolution

- `_resolve_persona_id(value, prompts)` — follows the same pattern as
  `_resolve_memory_entry_id` in `cli.py`.
- `disable <handle>` and `enable <handle>` call `repo.set_disabled(id, True/False)`.
- `show <handle>` and `delete <handle>` use the same resolve pattern.
- `delete` against a static persona ID prints an error (not supported).

## REPL

### New Command: `:persona` / `:p`

Registered in `_INTERACTIVE_COMMANDS` and dispatched in
`_handle_interactive_command` following the same pattern as `:reason`.

```
:persona              → alias for :persona list
:persona list         → same as CLI persona list
:persona show <handle>
:persona delete <handle>
:persona disable <handle>
:persona enable <handle>
```

Bare `:persona` or `:p` without arguments lists all personas with visible
index markers.

## Agent Tools

### New Tools

```python
persona_disable(persona: str) -> str
persona_enable(persona: str) -> str
```

- `persona` is a name or id (not a handle — agents see the resource, not CLI).
- Returns success/error message.
- Writes a trace for the action.

### Modified Tools

- **`persona_list`**: Excludes disabled personas by default. Pass
  `include_disabled=True` to include them (for agent awareness).
- **`persona_think`**: Raises a clear error if the target persona is disabled:
  `"Persona 'X' is disabled. Use persona_enable to reactivate it."`

These tools are registered in the shared tool pool via `build_persona_tools`.
The reason-thread-scoped variants (`build_reason_persona_tools`) also follow
these rules for **global** personas. Thread-scoped (local) personas are
unaffected by global disable/enable.

Both global and reason-thread `persona_think` use the shared free-text Agent
contract. A typed `AgentError` becomes the existing sanitized tool error
string. Raw `RuntimeError` or `ValueError` from an injected Agent
implementation propagates unchanged instead of masquerading as an expected
model availability or output failure.

## Activation Policy

### AgentBackedActivationPolicy

The activation policy (`persona/graph.py`, `AgentBackedActivationPolicy`) should
**not** present disabled personas to the LLM for selection. The `decide` method
receives only `BUILTIN_PERSONAS` (static) unless dynamic personas are loaded
via `load_persona_definitions`.

Currently, `load_persona_definitions()` loads custom persona instructions from
memory. The activation policy operates on `PersonaDefinition` (which has no
`disabled` flag). Dynamic `PersonaPrompt` personas are **not** part of the
activation policy — they are tool-callable only.

Failure to load the memory-backed instruction set is an observable degraded
mode, not an empty result. It returns the static builtins and records
`persona_definition_load_failed` through the Persona sealed audit registry;
diagnostic storage failure cannot replace that fallback.

**Design decision**: Since dynamic personas are tool-called (not activated),
the activation policy is **unchanged**. The disable filter applies at the
tool level (`persona_list`, `persona_think`) and at the CLI/REPL.

If in the future dynamic personas are lifted into the activation policy,
the `PersonaDefinition` model would need a `disabled` field, and
`load_persona_definitions()` would filter disabled entries.

## Trace Recording

- `persona disabled` → trace kind `persona_disabled` (new)
- `persona enabled` → trace kind `persona_enabled` (new)

Both records include `persona_prompt_id` and `name`. These are recorded in
`TraceService`.

## Migration

Existing persona files on disk lack the `disabled` field. The `from_wire`
method defaults to `False`, so existing personas remain active. No explicit
migration step is needed.

Old reason-thread persona JSON is workspace scratch rather than authoritative
global state and is intentionally not migrated when thread personas move to
the scoped SQLite workspace collection.

## Non-Goals

- No static persona disable/enable. Built-in personas are conceptually part
  of the core system and not user-manageable.
- No persona edit via CLI (use `persona_craft` / `persona create` for that).
- No bulk operations (disable all, enable all — add later if needed).
- No per-thread persona disable (thread-scoped personas are already isolated).
