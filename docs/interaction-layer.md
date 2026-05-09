# Interaction Layer Architecture

NuSelf is primarily a command-line application with a local background daemon. The CLI should feel useful both as a direct chat tool and as a control surface for a persistent personal agent that can think in the background, maintain memory, and notify the user when something is worth reopening.

## Goals

- Start a daemon explicitly or let commands attach to an existing daemon.
- Start chatting immediately from a new process when no daemon is running.
- Resume an existing conversation thread or create a new one from the CLI.
- Manage memory as clear, inspectable entries that can be reviewed, edited, deleted, and re-indexed.
- Let the daemon occasionally trigger self-reflection without becoming noisy.
- Notify the user through logs, email, or macOS notifications only after relevance gating.
- Keep CLI and daemon protocol aligned with current design; do not preserve obsolete command names or protocol fields during early development.

## Process Model

```text
CLI process
  -> Daemon client
    -> Existing daemon over local IPC
    -> Or starts an embedded one-shot runtime when requested

Daemon process
  -> LangGraph runtime
  -> Thread/session registry
  -> Memory entry service
  -> Proactive reflection scheduler
  -> Notification outbox dispatcher
```

The daemon owns long-lived state, active graph execution, background reflection, outbox delivery, and local indexes. CLI commands should be thin clients that send typed requests and render typed responses.

## Local IPC

Use a local Unix domain socket for the first implementation.

Default paths:

- Socket: `private/runtime/nuself.sock`
- Daemon pid file: `private/runtime/nuself.pid`
- Daemon log: `private/logs/daemon.log`
- Outbox log: `private/logs/outbox.log`

These paths live under ignored `private/` because they may reveal personal thread names, source names, or notification contents.

Initial protocol:

- JSON lines over the socket.
- Request and response objects with explicit `type`, `request_id`, and `version`.
- Streaming chat responses as typed events.
- Plain error responses with machine-readable codes and human-readable messages.

The protocol should remain independent from LangGraph internals. The daemon may use LangGraph thread IDs internally, but the CLI should interact through NuSelf thread commands and returned metadata.

During early development, protocol changes should be direct migrations. Update the server, client, tests, examples, and docs together instead of carrying old wire formats.

## CLI Shape

Use one executable, tentatively `nuself`.

Core commands:

```text
nuself daemon start
nuself daemon stop
nuself daemon restart
nuself daemon status
nuself daemon list
nuself daemon logs
nuself daemon attach

nuself chat
nuself chat --message "..."

nuself attach
nuself attach --message "..."

nuself thread list
nuself thread show <thread-id>
uself thread create <thread-id>
nuself thread rename <old-id> <new-id>
nuself thread branch <source-id> <new-id> [--index <n>]
nuself thread archive <thread-id>
nuself thread unarchive <thread-id>
nuself thread archived
nuself thread delete <thread-id>

nuself memory list
nuself memory preview
nuself memory show <entry-id>
nuself memory add --title "..." --body "..."
nuself memory edit <entry-id>
nuself memory delete <entry-id>
nuself memory search <query>
nuself memory stats
nuself memory relations
nuself memory graph <subcommand>
nuself memory update <entry-id>
nuself memory optimize
nuself memory export -o <path>
nuself memory import <path>
nuself memory profile <subcommand>
nuself memory candidate <subcommand>
nuself memory source <subcommand>
nuself memory reindex

nuself notify list
nuself notify show <entry-id>
nuself notify send <entry-id>
nuself notify dismiss <entry-id>
nuself notify clear

nuself eval --component <conversations|notifications|all>
nuself status
nuself health
nuself config
nuself logs
nuself open <thread-id>
nuself open --deep-link "nuself://thread/<id>"
```

The default `nuself chat` behavior:

- If a daemon is running, connect to it and create or resume the shared default working-memory stream.
- If no daemon is running, start an embedded one-shot runtime for immediate chat unless `--require-daemon` is set.
- If daemon auto-start is enabled later, start the daemon and then attach.
- Without `--message`, `chat`, `attach`, and `daemon attach` stay in an interactive loop until `:q`, `:quit`, `:exit`, or EOF.
- `nuself` is the shortest daemon-backed entrypoint: it connects to the current daemon, or creates a new daemon and then connects.
- `nuself daemon` without a subcommand shows daemon subcommand help.
- Interactive input starting with `:` is always parsed as a command. Unknown commands print interactive help and keep the session open.
- Interactive mode should use readline-backed line editing and arrow-key history when available, persisted under `private/runtime/interactive_history`.

## Chat Modes

### Attached Chat

Attached chat connects to the daemon and uses the shared working-memory stream. This is the default long-term mode.

Use cases:

- Continue the current NuSelf mind from another terminal.
- Open a proactive idea from a notification.
- Let background memory and indexes stay warm.

Multiple terminal attachments to the same daemon should share short-term working memory. Writes to the default stream must be serialized with a lock. Future branch threads may create alternate working-memory streams, but they should still share long-term memory by default.

### One-Shot Chat

One-shot chat starts a local runtime inside the CLI process when no daemon is available.

Use cases:

- First-run experience.
- Debugging.
- Temporary discussion without leaving a daemon running.

One-shot chat may still write the resulting working-memory stream and memory candidates to `private/`, but it should not start the proactive scheduler.

### Notification-Opened Chat

Notifications should include a deep link or command payload that resolves to:

- Existing thread ID, if the idea continues prior discussion.
- New thread seed, if the idea came from background reflection.
- Outbox intent ID, so the opened chat can show why the notification was sent.

## Memory Entry Model

Private memory must be manageable as clear entries, not only as raw files or opaque vector chunks.

Entry types:

- `source_note`: user-authored source material.
- `profile_fact`: reviewed durable fact or preference.
- `belief`: durable claim about worldview or reasoning.
- `style_trait`: communication or thinking style.
- `episode`: event, experience, or conversation-derived memory.
- `open_question`: unresolved question worth revisiting.
- `instruction`: procedural memory for the mirror or a persona.

Each memory entry should include:

- Stable entry ID.
- Type.
- Title.
- Body.
- Tags.
- Source references.
- Confidence.
- Privacy level.
- Created and updated timestamps.
- Review state.
- Optional expiration or revisit date.

Storage can begin as JSONL or TOML/Markdown files under `private/memory/entries/`, while raw imported documents remain under `private/sources/`. Indexes and embeddings should be derived artifacts under `private/derived/`.

## Memory Review Flow

Memory writes should be explicit:

```text
conversation or ingestion
  -> memory candidate
  -> review queue
  -> accept, edit, reject, or merge
  -> durable memory entry
  -> re-index
```

The CLI must make common review operations easy:

- List pending candidates.
- Show evidence for a candidate.
- Accept as-is.
- Edit before accepting.
- Merge into an existing entry.
- Reject with a reason.
- Delete an entry and rebuild indexes.

## Proactive Reflection

The daemon can trigger background reflection from two sources:

- Scheduled low-frequency timers.
- Events such as new memory entries, new source imports, or unresolved open questions.

Reflection must be rate-limited. Initial defaults:

- No more than 1 scheduled reflection run per 12 hours.
- No more than 1 user-visible notification per 24 hours unless priority is high.
- Event-triggered reflection should debounce for at least 30 minutes.
- Quiet hours should suppress notifications but still allow outbox logging.

Reflection output should become `IdeaCandidate` records first. Only candidates that pass the relevance gate become `NotificationIntent` records.

## Notification Channels

Notification delivery is adapter-based.

Initial channels:

- Log only: always available and safest.
- macOS notification: local prompt with a deep link or suggested command.
- Email: optional, configured from ignored private settings.

All channels read from the outbox. Graph nodes are allowed to propose notification intents, but only the dispatcher sends them.

Delivery policy fields:

- Channel allowlist.
- Priority.
- Cooldown key.
- Quiet-hours behavior.
- Require manual send.
- Max delivery attempts.

## First Implementation Slice

The interaction layer is now fully implemented through the first 10 steps:

1. ✅ CLI skeleton and command routing (`nuself` with subcommands).
2. ✅ Daemon start/status/stop with pid file and socket path under `private/runtime/`.
3. ✅ JSONL socket protocol with health check and daemon-backed chat request.
4. ✅ Memory entry CRUD over local files.
5. ✅ Memory-aware chat agent using OpenAI-compatible model calls when configured.
6. ✅ Thread registry with persisted messages and compressed conversation summaries under `private/threads/`.
7. ✅ Proactive reflection scheduler with interval, cooldown, quiet hours, and daemon background thread.
8. ✅ Outbox and log-only notification adapter.
9. ✅ macOS notification adapter via `osascript`.
10. ✅ Email adapter via SMTP with `private/email.toml` configuration.

Additional completed work beyond the initial slice:

- Deep links (`nuself://thread/<id>`) connect notifications to threads.
- `nuself open --deep-link` resolves and opens notification targets.
- REPL tab completion for commands, thread IDs, and archived thread IDs.
- `:whoami`, `:notify`, `:history`, `:sources`, `:search`, `:archive`, `:unarchive`, `:archived`, `:delete`, and command hints in the REPL.
- `nuself status` shows daemon, threads, and pending notifications.
- `nuself health` reports configuration and daemon health.
- `nuself config` shows project paths and API configuration status.
- Thread lifecycle: `create`, `rename`, `branch`, `archive`, `unarchive`, `archived`, `delete`.
- Memory import/export via JSON.
- Evaluation harness with conversation and notification fixtures.
- `IdeaCandidateGenerator` and `RelevanceGate` for context-aware reflection.
