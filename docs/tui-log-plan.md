# TUI And Logging Plan

This plan defines a short interaction polish slice before returning to the persona-runtime work. The goal is not to build a terminal dashboard or complex layout. NuSelf should stay REPL-shaped: the user types, NuSelf answers, and compact activity lines appear in order when background work happens.

## Goals

- Make interactive chat feel like a persistent local companion while keeping the REPL flow simple.
- Make daemon, chat, memory, and future notification activity observable from one consistent log surface.
- Show compact, colorful background activity while the user is in interactive chat.
- Make private memory easier to inspect from the same REPL without forcing the user to leave the conversation.
- Keep private data under ignored `private/` paths.
- Preserve the current daemon protocol unless a specific logging or TUI feature needs a typed response change.
- Keep implementation small enough to finish before returning to persona activation and routing.

## Non-Goals

- Full web UI.
- Cross-platform desktop app.
- Dashboard-style terminal panes or complex layouts.
- Rich multi-pane knowledge browser.
- Streaming token protocol overhaul.
- Remote log aggregation.
- Public telemetry.
- Replacing existing `nuself memory ...` maintenance commands.

## Current Baseline

- `nuself chat`, `nuself attach`, and `nuself daemon attach` share a readline-backed interactive loop.
- Interactive mode supports `:q`, `:quit`, `:exit`, `:memory`, and command help.
- The daemon writes stdout and stderr to `private/logs/daemon.log`.
- Memory curator and optimizer append action lines to `private/logs/memory.log`.
- `nuself daemon logs` prints the whole daemon log file.
- `:memory` already previews current memory entries inside interactive chat.
- Existing `nuself memory ...` commands cover entries, candidates, relations, graph traversal, sources, source chunks, profile items, stats, and reindexing.
- There is no unified log model, log filtering, tailing, structured event metadata, or REPL inspect surface beyond `:memory`.

## Planning Sources

This plan is grounded in the current checkout rather than a new UI concept:

- `README.md` documents memory entry commands: `memory list`, `preview`, `show`, `edit`, `search`, `update`, `optimize`, `delete`, and `reindex`.
- `README.md` documents inspect commands for derived relations and symbolic graph: `memory relations`, `memory graph nodes`, `memory graph edges`, `memory graph search`, closure traversal, and path finding.
- `README.md` documents source inspection: `memory source list`, `show`, `chunks`, `search`, `extract`, and `delete`.
- `README.md` documents profile inspection: `memory profile list`, `search`, `show`, and `delete`.
- `docs/memory-management.md` explicitly names future interactive memory commands: `:mem`, `:mem last`, and `:mem why`.
- `src/nuself/cli.py` already exposes the command handlers and formatters that the REPL inspect layer should reuse.
- `tests/test_cli.py` already covers interactive `:memory`, memory stats/search, relations, graph nodes/edges/search, source inspection, profile inspection, and candidate review flows.

## REPL Interaction Direction

Keep the first interaction layer as a terminal-native REPL around existing commands. It should improve visibility without changing core chat semantics or introducing a complex layout model.

### First Slice

- Add a dedicated interactive session renderer module under `src/nuself/tui/`, but keep it line-oriented.
- Keep standard-library rendering first: stable prompts, compact separators, status summaries, and command output blocks.
- Preserve readline history when available.
- Print a compact session header at startup with daemon status and thread ID.
- Print compact inline activity events during interactive chat so the user can see what the background system is doing without opening a separate log command.
- Add interactive commands:
  - `:help` shows commands.
  - `:status` shows daemon/socket/thread status.
  - `:logs` shows recent relevant log lines.
  - `:memory` keeps the existing memory preview behavior.
  - `:mem ...` adds compact memory inspection shortcuts.
  - `:clear` redraws the session view.
- Keep non-interactive `--message` output plain and script-friendly.

### Later Slice

- Consider a richer optional TUI dependency only if the simple REPL proves insufficient.
- If adopted, prefer an optional dependency group instead of making normal CLI startup require it.
- Avoid navigable panes unless there is a concrete workflow that cannot be served by ordered REPL output.

## Interactive Activity Feed

The interactive session should display selected log events as compact lines in the normal REPL output stream. It should be useful enough for daily work, but restrained enough that it does not drown out the conversation.

Example shape:

```text
[memory] + candidate=mem_123 title="prefers concise plans"
[daemon] request chat completed 420ms
[agent] graph detect_tool_request -> finalize_response
[selves] analyst_self noted 2 assumptions; skeptic_self raised 1 concern
```

Rendering rules:

- Use ANSI colors only when stdout is a TTY and color is not disabled.
- Keep each activity line to one terminal line when practical.
- Preserve chronological order. Do not rearrange events into panels.
- Use stable component tags such as `[daemon]`, `[chat]`, `[memory]`, `[agent]`, `[selves]`, and `[outbox]`.
- Use colors semantically: muted daemon lifecycle, blue chat/runtime, green memory writes, yellow warnings, red errors, purple persona/self discussion.
- Hide verbose metadata by default; expose detail through `:logs`, `nuself logs --json`, or a later debug mode.
- Never print raw private memory bodies or full chat transcripts as activity events.

Activity events can be sourced from:

- The response payload for events caused by the current user turn, such as memory curation summaries.
- Recent local JSONL log records after each turn.
- Future streaming daemon events if the socket protocol later supports them.

The first implementation can poll recent log records after each turn instead of introducing a streaming protocol. Streaming can wait until chat responses themselves become typed event streams.

### Persona Discussion Events

When persona discussion lands, the activity feed should be able to render bounded internal discussion without making it the final answer.

First persona activity events should be summaries, not full hidden chain-of-thought:

- Which personas were selected.
- Why persona discussion was triggered: explicit user request, high-depth topic, personal-memory relevance, or high-impact advice.
- Counts of notes, concerns, questions, and evidence references.
- Synthesizer decision: answer, ask clarification, create memory candidate, or skip.

The user can ask to show more discussion detail later, but the default interactive output should stay compact and avoid exposing unrestricted model reasoning.

## Memory Inspect Surface

The REPL should make the existing memory system easier to inspect without replacing maintenance commands. Use compact shortcuts for common reading tasks, and keep write/review operations explicit through `nuself memory ...` unless a later workflow clearly needs interactive review.

### First Slice

Add these interactive commands:

- `:mem` or `:memory`: preview recent memory entries.
- `:mem search <query>`: search memory entries with compact match output.
- `:mem show <entry-id>`: show one memory entry.
- `:mem candidates`: list pending memory candidates.
- `:mem candidate <candidate-id>`: show one candidate.
- `:mem profile <query>`: search profile items.
- `:mem sources`: list imported sources.
- `:mem source <source-id>`: show source metadata and chunk count.
- `:mem why`: explain the memory context used for the most recent answer when the runtime exposes that trace.

Keep output line-oriented:

```text
[mem] reviewed belief mem_123 Clarity matters most tags=style confidence=0.80
[mem] candidate cand_456 update -> mem_123 reason="duplicate preference"
[src] source_abc notes/my-note.md chunks=12 tags=notes
```

Implementation constraints:

- Reuse existing repository/query services and existing formatter logic where possible.
- Prefer IDs, titles, tags, confidence, review state, relation summaries, and evidence references over full bodies in list views.
- `show` commands may print full bodies because the user explicitly requested a specific object.
- Do not expose raw imported chunks unless the user explicitly asks for source chunks or source search detail.
- Keep write actions such as accept, reject, merge, edit, delete, and reindex on the normal CLI for now.

### Later Slice

- `:mem last`: show entries, profile items, source chunks, and graph relations packed into the last response context.
- `:mem graph <query>`: compact graph search from the REPL.
- `:mem relations <entry-id>`: show direct relation neighborhood around one memory object.
- `:mem path <from-id> <to-id>`: show path-finding output when IDs are known.
- `:mem source chunks <source-id>`: inspect chunks without leaving the REPL.
- Optional interactive candidate review can be added only after read-only inspect commands feel stable.

## Logging Direction

Logging should become structured at the write boundary while still being readable with plain text tools.

### Log Files

- `private/logs/daemon.log`: daemon lifecycle, socket handling, request failures, background job failures.
- `private/logs/chat.log`: chat turns, thread IDs, runtime outcomes, graph diagnostics summaries.
- `private/logs/memory.log`: curator and optimizer actions, already present.
- `private/logs/persona.log`: future persona activation, routing, bounded discussion summaries, and synthesizer decisions.
- `private/logs/outbox.log`: future notification/outbox delivery events, already planned.

### Event Shape

Use JSON Lines for new structured logs:

```json
{"time":"2026-05-08T12:00:00+08:00","level":"info","component":"chat","event":"turn_completed","thread_id":"default","message":"chat turn completed"}
```

Required fields:

- `time`
- `level`
- `component`
- `event`
- `message`

Optional fields:

- `thread_id`
- `request_id`
- `node`
- `duration_ms`
- `status`
- `error`
- `metadata`

Optional persona fields:

- `trigger`
- `selected_personas`
- `contribution_count`
- `concern_count`
- `question_count`
- `synthesizer_action`

### Privacy Rules

- Do not log full user messages by default.
- Do not log full assistant answers by default.
- Do not log raw memory bodies, source chunks, or profile text.
- Do not log unrestricted persona reasoning or hidden chain-of-thought.
- Log stable IDs, counts, summaries, statuses, and diagnostics.
- Allow explicit debug logging later through ignored private configuration.

### CLI Surface

- Extend `nuself daemon logs` into a general log viewer:
  - `nuself logs`
  - `nuself logs --component daemon`
  - `nuself logs --component chat`
  - `nuself logs --component memory`
  - `nuself logs --tail 50`
  - `nuself logs --follow`
- Keep `nuself daemon logs` as a thin alias while the daemon command group remains.
- Render JSONL logs as concise text by default.
- Provide `--json` for raw log records.

## Implementation Order

1. Add a small structured logging module with JSONL append helpers and safe field normalization.
2. Route daemon lifecycle and daemon request errors through the new logger.
3. Add `chat.log` entries around conversation runtime completion and failures without storing message bodies.
4. Add `nuself logs` with component filtering, tail count, and plain rendering.
5. Add compact color rendering for structured log records.
6. Refactor interactive loop rendering into a line-oriented `tui` module without changing chat behavior.
7. Print selected background activity events during interactive chat after each turn.
8. Add `:status` and `:logs` commands to interactive mode.
9. Add read-only `:mem ...` inspection commands that reuse existing memory repositories and formatters.
10. Reserve persona activity event fields for the later multi-persona routing work.
11. Update README and Chinese README command docs after the user-facing CLI surface lands.

## Validation

- `uv run pytest tests/test_cli.py tests/test_daemon_server.py`
- Focused tests for JSONL log writing and redaction.
- CLI tests for `nuself logs --tail`, missing log files, and component filtering.
- Rendering tests for compact colored and no-color log output.
- Interactive command tests for `:status`, `:logs`, and existing `:memory`.
- Interactive command tests for `:mem search`, `:mem show`, `:mem candidates`, `:mem profile`, and `:mem sources`.
- Interactive tests proving activity output does not include raw private message bodies.
- Inspect-output tests proving list/search views stay compact while explicit show views can include object bodies.
- `uvx pyright`
- Full `uv run pytest` before merging back to `main`.

## Commit Plan

1. `docs(cli): plan TUI and logging polish`
2. `feat(logging): add structured local log writer`
3. `feat(cli): add log viewer commands`
4. `feat(cli): render compact log events`
5. `feat(tui): extract interactive session renderer`
6. `feat(tui): show interactive activity events`
7. `feat(tui): add status and log commands`
8. `feat(tui): add memory inspect commands`
9. `docs(cli): update TUI and logging progress`

After these are implemented and reviewed, merge this branch back to `main` and resume the persona activation/routing focus.
