"""REPL subsystem command implementations and help text."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat.audit import report_chat_failure
from nuself.cli.daemon_lifecycle import (
    restart_daemon_observed,
)
from nuself.cli.daemon_status import format_status
from nuself.cli.application import cli_application
from nuself.cli.output import print_ansi
from nuself.cli.persona_management import (
    create_persona,
    delete_personas,
    list_persona_prompts,
    resolve_persona_id,
    set_persona_enabled,
)
from nuself.daemon import lifecycle
from nuself.handles import VisibleHandleError, resolve_visible_handle
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryEntryNotFound,
)
from nuself.memory.source_repository import (
    SourceDocumentNotFound,
)
from nuself.persona.audit import report_persona_failure
from nuself.reason.errors import ReasonError, ReasonNotFound
from nuself.reflection.repository import ReflectionEntryNotFound
from nuself.runtime.diagnostics import (
    diagnostic_exception_chain,
    diagnostic_exception_message,
)
from nuself.trace.repository import TraceNotFound
from nuself.tui.memory import (
    render_candidate_detail,
    render_candidate_row,
    render_memory_entry_detail,
    render_memory_entry_row,
    render_profile_row,
    render_source_detail,
    render_source_row,
)
from nuself.tui.reason import render_reason_detail, render_reason_row
from nuself.tui.render import TerminalTheme
from nuself.tui.trace import render_trace_detail, render_trace_row

theme = TerminalTheme()


def handle_interactive_memory_command(command: str, project_root: Path | None) -> str:
    if command == "why":
        return "No memory-context trace is available for the last answer yet."
    if command.startswith("search "):
        query = command.removeprefix("search ").strip()
        entries = cli_application().memory.entries.search(query)
        if not entries:
            return "No matching memory entries."
        return "\n".join(
            render_memory_entry_row(entry) for entry in entries
        )
    memory = cli_application().memory
    if command.startswith("show "):
        entry_id = command.removeprefix("show ").strip()
        try:
            entry_id = resolve_visible_handle(
                entry_id,
                memory.entries.list(),
                label="memory",
                get_id=lambda entry: entry.id,
            )
        except VisibleHandleError as exc:
            return diagnostic_exception_message(exc)
        try:
            entry = memory.entries.get(entry_id)
        except MemoryEntryNotFound:
            return f"Memory entry not found: {entry_id}"
        return render_memory_entry_detail(entry)
    if command == "review":
        candidates = memory.candidates.list()
        if not candidates:
            return "No memory candidates."
        return "\n".join(render_candidate_row(candidate, index=index) for index, candidate in enumerate(candidates))
    if command.startswith("review "):
        candidate_id = command.removeprefix("review ").strip()
        try:
            candidate_id = resolve_visible_handle(
                candidate_id,
                memory.candidates.list(),
                label="memory candidate",
                get_id=lambda candidate: candidate.id,
            )
        except VisibleHandleError as exc:
            return diagnostic_exception_message(exc)
        try:
            candidate = memory.candidates.get(candidate_id)
        except MemoryCandidateNotFound:
            return f"Memory candidate not found: {candidate_id}"
        return render_candidate_detail(candidate)
    if command.startswith("profile "):
        query = command.removeprefix("profile ").strip()
        items = memory.profile.search(query)
        if not items:
            return "No matching profile items."
        return "\n".join(render_profile_row(item) for item in items)
    if command == "sources":
        repo = memory.sources
        documents = repo.list_documents()
        if not documents:
            return "No source documents."
        return "\n".join(
            render_source_row(document, index=index, chunk_count=len(repo.list_chunks(document.id)))
            for index, document in enumerate(documents)
        )
    if command.startswith("source "):
        source_id = command.removeprefix("source ").strip()
        repo = memory.sources
        try:
            source_id = resolve_visible_handle(
                source_id,
                repo.list_documents(),
                label="source document",
                get_id=lambda document: document.id,
            )
        except VisibleHandleError as exc:
            return diagnostic_exception_message(exc)
        try:
            document = repo.get_document(source_id)
        except SourceDocumentNotFound:
            return f"Source document not found: {source_id}"
        return render_source_detail(document, chunk_count=len(repo.list_chunks(document.id)))
    return interactive_memory_help(command)


def handle_interactive_reason_command(command: str, project_root: Path | None) -> str:
    service = cli_application().reason_service
    if command == "":
        return interactive_reason_help()
    if command == "list":
        threads = service.list_threads(status="all")
        if not threads:
            return "No reason threads."
        return "\n".join(render_reason_row(thread, index=index) for index, thread in enumerate(threads))
    if command.startswith("show "):
        thread_ref = command.removeprefix("show ").strip()
        try:
            thread = service.show_thread(thread_ref)
        except ReasonNotFound:
            return f"Reason thread not found: {thread_ref}"
        steps = service.list_steps(thread.id)
        return render_reason_detail(thread, steps)
    if command.startswith("start "):
        question = command.removeprefix("start ").strip()
        try:
            thread = service.start_thread(question)
        except ReasonError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Started reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("advance "):
        thread_ref = command.removeprefix("advance ").strip()
        from nuself.reason.composition import compose_reason_advancer

        application = cli_application()
        advancer = compose_reason_advancer(
            application.paths,
            application.reason_workspace,
            application.persona_prompts,
            application.trace.recorder,
            application.config,
        )
        try:
            thread = service.advance_thread(
                thread_ref,
                advancer=advancer,
            )
        except ReasonError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Advanced reason thread: {thread.id}\n{render_reason_detail(thread, service.list_steps(thread.id))}"
    if command.startswith("pause "):
        thread_ref = command.removeprefix("pause ").strip()
        try:
            thread = service.pause_thread(thread_ref)
        except ReasonError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Paused reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("resume "):
        thread_ref = command.removeprefix("resume ").strip()
        try:
            thread = service.resume_thread(thread_ref)
        except ReasonError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Resumed reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("resolve "):
        thread_ref = command.removeprefix("resolve ").strip()
        try:
            thread = service.resolve_thread(thread_ref)
        except ReasonError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Resolved reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("archive "):
        thread_ref = command.removeprefix("archive ").strip()
        try:
            thread = service.archive_thread(thread_ref)
        except ReasonError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Archived reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("delete "):
        thread_ref = command.removeprefix("delete ").strip()
        try:
            tid = service.delete_thread(thread_ref)
        except ReasonError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Deleted reason thread: {tid}"
    return interactive_reason_help(command)


def interactive_reason_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown reason command: :reason {command}")
    lines.extend(
        [
            "Reason commands:",
            "  :reason",
            "  :reason list",
            "  :reason show <id|index>",
            "  :reason start <topic>",
            "  :reason advance <id|index>",
            "  :reason pause <id|index>",
            "  :reason resume <id|index>",
            "  :reason resolve <id|index>",
            "  :reason archive <id|index>",
            "  :reason delete <id|index>",
            "  :reason watch              watch for new reasoning steps (Ctrl+C to stop)",
        ]
    )
    return "\n".join(lines)


def handle_interactive_trace_command(command: str, project_root: Path | None) -> str:
    service = cli_application().trace.query
    if command in {"", "list"}:
        traces = service.list_traces()
        if not traces:
            return "No trace records."
        return "\n".join(render_trace_row(trace, index=index) for index, trace in enumerate(traces))
    if command.startswith("show "):
        trace_id = command.removeprefix("show ").strip()
        try:
            trace = service.show_trace(trace_id)
        except TraceNotFound:
            return f"Trace not found: {trace_id}"
        return render_trace_detail(trace, service.links_for(trace.id))
    if command.startswith("search "):
        query = command.removeprefix("search ").strip()
        traces = service.search_traces(query)
        if not traces:
            return "No matching trace records."
        return "\n".join(render_trace_row(trace, index=index) for index, trace in enumerate(traces))
    if command.startswith("related "):
        artifact_ref = command.removeprefix("related ").strip()
        traces = service.traces_for_artifact(artifact_ref)
        links = service.links_for_artifact(artifact_ref)
        if not traces and not links:
            return f"No trace records or links related to: {artifact_ref}"
        lines = [render_trace_row(trace, index=index) for index, trace in enumerate(traces)]
        if links:
            if lines:
                lines.append("")
            lines.append("Related links:")
            lines.extend(f"  {link.relation}: {link.source_id} -> {link.target_id} ({link.summary})" for link in links)
        return "\n".join(lines)
    return interactive_trace_help(command)


def handle_interactive_persona_command(command: str, project_root: Path | None) -> str:
    try:
        from nuself.tui.persona import render_persona_detail, render_persona_row

        repo = cli_application().persona_prompts
        if command in {"", "list"}:
            prompts = list_persona_prompts(project_root)
            if not prompts:
                return f"{theme.tag('[persona]', 'persona')} {theme.muted('No custom personas yet')}"
            blocks: list[str] = [f"{theme.tag('[persona]', 'persona')} Custom personas (dynamic):"]
            for i, p in enumerate(prompts):
                blocks.append(render_persona_row(p, index=i))
            return "\n".join(blocks)
        if command.startswith("show "):
            persona_id = command.removeprefix("show ").strip()
            resolved = resolve_persona_id(project_root, persona_id)
            if resolved is None:
                return f"{theme.tag('[persona]', 'persona')} {theme.error('Not found')}: {persona_id}"
            prompt = repo.get(resolved)
            if prompt is None:
                return f"{theme.tag('[persona]', 'persona')} {theme.error('Not found')}: {persona_id}"
            return render_persona_detail(prompt)
        if command.startswith("delete "):
            persona_id = command.removeprefix("delete ").strip()
            delete_personas(project_root, persona_id)
            return ""
        if command.startswith("disable "):
            persona_id = command.removeprefix("disable ").strip()
            set_persona_enabled(
                project_root,
                persona_id,
                enabled=False,
            )
            return ""
        if command.startswith("enable "):
            persona_id = command.removeprefix("enable ").strip()
            set_persona_enabled(
                project_root,
                persona_id,
                enabled=True,
            )
            return ""
        if command.startswith("create "):
            rest = command.removeprefix("create ").strip()
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                return f"{theme.tag('[persona]', 'persona')} {theme.error('Usage')}: :persona create <name> <prompt>"
            name, prompt_text = parts
            create_persona(project_root, name, prompt_text)
            return ""
        return interactive_persona_help(command)
    except Exception as exc:
        action = command.split(maxsplit=1)[0] if command else "list"
        report_persona_failure(
            exc,
            event="interactive_command_failed",
            project_root=project_root,
            metadata={"action": action},
        )
        return (
            f"{theme.tag('[persona]', 'persona')} "
            f"{theme.error(diagnostic_exception_message(exc))}"
        )


def handle_interactive_restart_command(project_root: Path | None) -> str:
    scope = cli_application().paths.scope
    try:
        result = restart_daemon_observed(scope)
    except (lifecycle.DaemonStopError, lifecycle.DaemonStartError) as exc:
        return (
            "Failed to restart daemon: "
            f"{diagnostic_exception_message(exc)}"
        )
    return (
        f"Restarted daemon: {format_status(result.start.status)} "
        f"stop={result.stop.outcome} start={result.start.outcome}"
    )


def interactive_persona_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown persona command: :persona {command}")
    lines.extend(
        [
            "Persona commands:",
            "  :persona",
            "  :persona list",
            "  :persona show <id|index>",
            "  :persona create <name> <prompt>",
            "  :persona delete <id|index>",
            "  :persona disable <id|index>",
            "  :persona enable <id|index>",
        ]
    )
    return "\n".join(lines)


def interactive_trace_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown trace command: :trace {command}")
    lines.extend(
        [
            "Trace commands:",
            "  :trace",
            "  :trace list",
            "  :trace show <id|index>",
            "  :trace search <query>",
            "  :trace related <artifact_ref>",
        ]
    )
    return "\n".join(lines)


def interactive_memory_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown memory command: :mem {command}")
    lines.extend(
        [
            "Memory commands:",
            "  :mem search <query>",
            "  :mem show <entry-id|index>",
            "  :mem review",
            "  :mem review <candidate-id|index>",
            "  :mem profile <query>",
            "  :mem sources",
            "  :mem source <source-id|index>",
            "  :mem why",
        ]
    )
    return "\n".join(lines)


def handle_interactive_history_command(project_root: Path | None, conversation_id: str) -> str:
    try:
        state = cli_application().conversations.load(
            conversation_id
        )
    except Exception as exc:
        report_chat_failure(
            exc,
            event="interactive_history_load_failed",
            project_root=project_root,
            metadata={"conversation_id": conversation_id},
        )
        return (
            f"Unable to load conversation history for '{conversation_id}': "
            f"{diagnostic_exception_chain(exc)}"
        )
    if not state.messages:
        return "No messages in this conversation."
    lines = [f"Recent messages in '{conversation_id}':"]
    for msg in state.messages[-10:]:
        prefix = ">" if msg.role == "user" else "<"
        content = msg.content[:120]
        if len(msg.content) > 120:
            content += "..."
        lines.append(f"  {prefix} {content}")
    return "\n".join(lines)


def handle_interactive_whoami_command(project_root: Path | None) -> str:
    repo = cli_application().memory.profile
    items = repo.list()
    if not items:
        return "No profile items yet."
    lines = ["Core profile:"]
    for item in items[:6]:
        lines.append(f"  {item.id}: {item.body[:80]}")
    if len(items) > 6:
        lines.append(f"  ... and {len(items) - 6} more")
    return "\n".join(lines)


def handle_interactive_reflection_command(
    project_root: Path | None,
    *,
    include_all: bool = False,
) -> str:
    from nuself.tui.render import render_reflection_entry_summary

    entries = cli_application().reflection_service.list_entries(
        status=None if include_all else "pending"
    )
    if not entries:
        return (
            "No reflection ideas."
            if include_all
            else "No pending reflection ideas."
        )
    lines = [
        "All reflection ideas:"
        if include_all
        else "Pending reflection ideas:"
    ]
    for idx, entry in enumerate(entries):
        lines.extend(
            f"  {line}" if line else ""
            for line in render_reflection_entry_summary(
                entry,
                index=idx,
            ).splitlines()
        )
    return "\n".join(lines)


def handle_interactive_inbox_command(project_root: Path | None) -> str:
    sections = [
        handle_interactive_reflection_command(project_root),
        handle_interactive_notify_command(project_root),
    ]
    return "\n\n".join(sections)


def handle_interactive_reflection_show_command(project_root: Path | None, entry_id: str) -> str:
    from nuself.tui.render import render_reflection_entry_detail

    try:
        entry = cli_application().reflection_service.show_entry(entry_id)
    except (ReflectionEntryNotFound, ValueError) as exc:
        return diagnostic_exception_message(exc)
    return render_reflection_entry_detail(entry)


def handle_interactive_reflection_subcommand(project_root: Path | None, subcmd: str, entry_id: str) -> str:
    service = cli_application().reflection_service
    try:
        service.show_entry(entry_id)
    except (ReflectionEntryNotFound, ValueError) as exc:
        return diagnostic_exception_message(exc)
    if subcmd == "dismiss":
        entry = service.dismiss_entry(entry_id)
        return f"Dismissed: {entry.id}"
    if subcmd == "archive":
        entry = service.archive_entry(entry_id)
        return f"Archived: {entry.id}"
    if subcmd == "promote":
        try:
            thread = service.promote_to_reason(entry_id)
        except RuntimeError as exc:
            return f"Error: {diagnostic_exception_message(exc)}"
        return f"Promoted reflection to reason thread: {thread.id}\n{render_reason_detail(thread)}"
    return f"Unknown :inbox reflection subcommand: {subcmd}"


def handle_interactive_notify_command(
    project_root: Path | None,
    *,
    include_all: bool = False,
) -> str:
    from nuself.tui.render import render_outbox_summary

    outbox = cli_application().notifications
    entries = (
        outbox.list()
        if include_all
        else outbox.list(status="pending")
    )
    if not entries:
        return (
            "No notifications."
            if include_all
            else "No pending notifications."
        )
    lines = [
        "All notifications:"
        if include_all
        else "Pending notifications:"
    ]
    for index, entry in enumerate(entries):
        lines.append("  " + render_outbox_summary(entry, index=index))
    return "\n".join(lines)


def handle_interactive_notify_show_command(project_root: Path | None, entry_id: str) -> str:
    from nuself.notification.outbox import OutboxEntryNotFound
    from nuself.tui.render import render_outbox_detail

    try:
        entry = cli_application().notifications.get(
            entry_id
        )
    except OutboxEntryNotFound:
        return f"Outbox entry not found: {entry_id}"
    return render_outbox_detail(entry)


def handle_interactive_notify_subcommand(project_root: Path | None, subcmd: str, entry_id: str) -> str:
    from nuself.notification.delivery import deliver_entry_once
    from nuself.notification.outbox import OutboxEntryNotFound
    from nuself.notification.composition import (
        build_notification_adapters,
    )

    application = cli_application()
    outbox = application.notifications
    try:
        outbox.get(entry_id)
    except OutboxEntryNotFound:
        return f"Outbox entry not found: {entry_id}"
    if subcmd == "send":
        updated = deliver_entry_once(
            outbox,
            entry_id,
            build_notification_adapters(
                application.paths,
                email_config=application.config.email,
                macos_config=application.config.macos_notification,
            ),
        )
        if updated.status == "sent":
            return f"Sent: {entry_id}"
        return f"Failed to send: {entry_id}"
    if subcmd == "dismiss":
        outbox.dismiss(entry_id)
        return f"Dismissed: {entry_id}"
    return f"Unknown :inbox notify subcommand: {subcmd}"


def handle_interactive_watch_command(project_root: Path | None) -> None:
    import time

    from nuself.tui.render import render_outbox_summary

    outbox = cli_application().notifications
    seen: set[str] = set()
    for entry in outbox.list():
        seen.add(entry.id)

    print("Watching outbox. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(2)
            for entry in outbox.list():
                if entry.id not in seen:
                    seen.add(entry.id)
                    print_ansi(render_outbox_summary(entry))
    except KeyboardInterrupt:
        print("\nStopped watching.")


def handle_interactive_conversations_command(project_root: Path | None) -> str:
    store = cli_application().conversations
    ids = store.list()
    if not ids:
        return "No active conversations."
    return "Active conversations:\n" + "\n".join(f"  {tid}" for tid in ids)
