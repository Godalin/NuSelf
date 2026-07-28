"""REPL subsystem command implementations and help text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nuself.agent.chat import ThreadStore
from nuself.cli.commands.daemon import format_status
from nuself.cli.commands.output import print_ansi
from nuself.cli.commands.persona import (
    handle_persona_create,
    handle_persona_delete,
    handle_persona_disable,
    handle_persona_enable,
    resolve_persona_id,
)
from nuself.daemon import lifecycle
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryCandidateRepository,
    MemoryEntryNotFound,
    MemoryEntryRepository,
)
from nuself.memory.source_repository import (
    SourceDocumentNotFound,
    SourceRepository,
)
from nuself.logs import write_log_event
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.reason.repository import ReasonNotFound
from nuself.reason.service import ReasonService
from nuself.storage import auto_backend
from nuself.trace.repository import TraceNotFound
from nuself.trace.service import TraceQueryService
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


def indent_lines(lines: list[str], prefix: str) -> list[str]:
    return [f"{prefix}{line}" if line else "" for line in lines]


def handle_interactive_memory_search(query: str, project_root: Path | None) -> str:
    entries = MemoryEntryRepository(project_root).search(query)
    if not entries:
        return "No matching memory entries."
    return "\n".join(render_memory_entry_row(entry) for entry in entries)


def handle_interactive_memory_command(command: str, project_root: Path | None) -> str:
    if command == "why":
        return "No memory-context trace is available for the last answer yet."
    if command.startswith("search "):
        query = command.removeprefix("search ").strip()
        return handle_interactive_memory_search(query, project_root)
    if command.startswith("show "):
        entry_id = command.removeprefix("show ").strip()
        if entry_id.isdigit():
            entries = MemoryEntryRepository(project_root).list()
            index = int(entry_id)
            if 0 <= index < len(entries):
                entry_id = entries[index].id
        try:
            entry = MemoryEntryRepository(project_root).get(entry_id)
        except MemoryEntryNotFound:
            return f"Memory entry not found: {entry_id}"
        return render_memory_entry_detail(entry)
    if command == "review":
        candidates = MemoryCandidateRepository(project_root).list()
        if not candidates:
            return "No memory candidates."
        return "\n".join(render_candidate_row(candidate, index=index) for index, candidate in enumerate(candidates))
    if command.startswith("review "):
        candidate_id = command.removeprefix("review ").strip()
        if candidate_id.isdigit():
            candidates = MemoryCandidateRepository(project_root).list()
            index = int(candidate_id)
            if 0 <= index < len(candidates):
                candidate_id = candidates[index].id
        try:
            candidate = MemoryCandidateRepository(project_root).get(candidate_id)
        except MemoryCandidateNotFound:
            return f"Memory candidate not found: {candidate_id}"
        return render_candidate_detail(candidate)
    if command.startswith("profile "):
        query = command.removeprefix("profile ").strip()
        items = ProfileItemRepository(project_root).search(query)
        if not items:
            return "No matching profile items."
        return "\n".join(render_profile_row(item) for item in items)
    if command == "sources":
        repo = SourceRepository(project_root)
        documents = repo.list_documents()
        if not documents:
            return "No source documents."
        return "\n".join(
            render_source_row(document, index=index, chunk_count=len(repo.list_chunks(document.id)))
            for index, document in enumerate(documents)
        )
    if command.startswith("source "):
        source_id = command.removeprefix("source ").strip()
        repo = SourceRepository(project_root)
        if source_id.isdigit():
            documents = repo.list_documents()
            index = int(source_id)
            if 0 <= index < len(documents):
                source_id = documents[index].id
        try:
            document = repo.get_document(source_id)
        except SourceDocumentNotFound:
            return f"Source document not found: {source_id}"
        return render_source_detail(document, chunk_count=len(repo.list_chunks(document.id)))
    return interactive_memory_help(command)


def handle_interactive_reason_command(command: str, project_root: Path | None) -> str:
    service = ReasonService(project_root)
    if command == "":
        return interactive_reason_help()
    if command == "list":
        threads = service.list_threads(status="all")
        if not threads:
            return "No reason threads."
        return "\n".join(render_reason_row(thread, index=index) for index, thread in enumerate(threads))
    if command.startswith("show "):
        thread_id = command.removeprefix("show ").strip()
        try:
            thread = service.show_thread(thread_id)
        except ReasonNotFound:
            return f"Reason thread not found: {thread_id}"
        steps = service.list_steps(thread.id)
        return render_reason_detail(thread, steps)
    if command.startswith("start "):
        question = command.removeprefix("start ").strip()
        try:
            thread = service.start_thread(question)
        except RuntimeError as exc:
            return f"Error: {exc}"
        return f"Started reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("advance "):
        thread_id = command.removeprefix("advance ").strip()
        from nuself.llm import configured_langchain_chat_models
        from nuself.reason.advancer import ReasonAdvancer
        from nuself.workspace import PrivateWorkspaceStore

        advancer = ReasonAdvancer(project_root=project_root, workspace_store=PrivateWorkspaceStore(project_root, scope="reason"), langchain_models=configured_langchain_chat_models(project_root))
        service = ReasonService(project_root, advancer=advancer)
        try:
            thread = service.advance_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Advanced reason thread: {thread.id}\n{render_reason_detail(thread, service.list_steps(thread.id))}"
    if command.startswith("pause "):
        thread_id = command.removeprefix("pause ").strip()
        try:
            thread = service.pause_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Paused reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("resume "):
        thread_id = command.removeprefix("resume ").strip()
        try:
            thread = service.resume_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Resumed reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("resolve "):
        thread_id = command.removeprefix("resolve ").strip()
        try:
            thread = service.resolve_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Resolved reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("archive "):
        thread_id = command.removeprefix("archive ").strip()
        try:
            thread = service.archive_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Archived reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("delete "):
        thread_id = command.removeprefix("delete ").strip()
        try:
            tid = service.delete_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
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


def handle_interactive_reason_watch(project_root: Path | None, interval: int = 2, thread_ref: str | None = None) -> None:
    """Watch for new reasoning steps and print them.

    If *thread_ref* is given (id or index), watch only that thread.
    """
    import time

    from nuself.reason.service import ReasonService
    from nuself.reason.repository import ReasonNotFound
    from nuself.tui.reason import render_reason_detail, render_step_watch_entry

    service = ReasonService(project_root)
    threads = service.list_threads(status="all")
    if thread_ref is not None:
        try:
            thread = service.show_thread(thread_ref)
        except ReasonNotFound:
            print(f"Reason thread not found: {thread_ref}", file=sys.stderr)
            return
        threads = [thread]
        print_ansi(render_reason_detail(thread))
        for step in service.list_steps(thread.id):
            print_ansi(render_step_watch_entry(step))
    else:
        for index, thread in enumerate(threads):
            print_ansi(render_reason_detail(thread))
            print_ansi(theme.muted(f"(index: {index})"))
            for step in service.list_steps(thread.id):
                print_ansi(render_step_watch_entry(step))
    print()
    print("Watching for new reasoning steps. Press Ctrl+C to stop.")

    # Track step count per thread for polling.
    counts: dict[str, int] = {}
    for thread in threads:
        counts[thread.id] = len(service.list_steps(thread.id))

    try:
        while True:
            time.sleep(interval)
            for thread in threads:
                steps = service.list_steps(thread.id)
                if len(steps) > counts.get(thread.id, 0):
                    for step in steps[counts[thread.id]:]:
                        print_ansi(render_step_watch_entry(step))
                    counts[thread.id] = len(steps)
    except KeyboardInterrupt:
        print("\nStopped watching.")


def handle_interactive_trace_command(command: str, project_root: Path | None) -> str:
    service = TraceQueryService(project_root)
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

        repo = PersonaPromptRepository(
            backend=auto_backend(project_root),
            project_root=project_root,
        )
        if command in {"", "list"}:
            prompts = repo.list()
            if not prompts:
                return f"{theme.tag('[persona]', 'persona')} {theme.muted('No custom personas yet')}"
            blocks: list[str] = [f"{theme.tag('[persona]', 'persona')} Custom personas (dynamic):"]
            for i, p in enumerate(prompts):
                blocks.append(render_persona_row(p, index=i))
            return "\n".join(blocks)
        if command.startswith("show "):
            persona_id = command.removeprefix("show ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root)
            resolved = resolve_persona_id(args)
            if resolved is None:
                return f"{theme.tag('[persona]', 'persona')} {theme.error('Not found')}: {persona_id}"
            prompt = repo.get(resolved)
            if prompt is None:
                return f"{theme.tag('[persona]', 'persona')} {theme.error('Not found')}: {persona_id}"
            return render_persona_detail(prompt)
        if command.startswith("delete "):
            persona_id = command.removeprefix("delete ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root, yes=False)
            handle_persona_delete(args)
            return ""
        if command.startswith("disable "):
            persona_id = command.removeprefix("disable ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root, yes=False)
            handle_persona_disable(args)
            return ""
        if command.startswith("enable "):
            persona_id = command.removeprefix("enable ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root, yes=False)
            handle_persona_enable(args)
            return ""
        if command.startswith("create "):
            rest = command.removeprefix("create ").strip()
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                return f"{theme.tag('[persona]', 'persona')} {theme.error('Usage')}: :persona create <name> <prompt>"
            name, prompt_text = parts
            args = argparse.Namespace(name=name, prompt=prompt_text, project_root=project_root)
            handle_persona_create(args)
            return ""
        return interactive_persona_help(command)
    except Exception as exc:
        return f"{theme.tag('[persona]', 'persona')} {theme.error(str(exc))}"


def handle_interactive_restart_command(project_root: Path | None) -> str:
    write_log_event("daemon", "restart_requested", "daemon restart requested", project_root=project_root)
    stop_result = lifecycle.stop(project_root)
    if stop_result.running:
        return f"Failed to stop daemon: {format_status(stop_result)}"
    start_result = lifecycle.start(project_root)
    write_log_event(
        "daemon",
        "restart_completed",
        f"daemon restart {'completed' if start_result.running else 'failed'}",
        project_root=project_root,
        status="running" if start_result.running else "stopped",
        metadata={"pid": start_result.pid, "socket": str(start_result.socket_path)},
    )
    if not start_result.running:
        return f"Failed to restart daemon: {format_status(start_result)}"
    return f"Restarted daemon: {format_status(start_result)}"


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


def handle_interactive_history_command(project_root: Path | None, thread_id: str) -> str:
    from nuself.agent.chat import ThreadStore

    try:
        state = ThreadStore(project_root).load(thread_id)
    except Exception:
        return "No thread state available."
    if not state.messages:
        return "No messages in this thread."
    lines = [f"Recent messages in '{thread_id}':"]
    for msg in state.messages[-10:]:
        prefix = ">" if msg.role == "user" else "<"
        content = msg.content[:120]
        if len(msg.content) > 120:
            content += "..."
        lines.append(f"  {prefix} {content}")
    return "\n".join(lines)


def handle_interactive_whoami_command(project_root: Path | None) -> str:
    repo = ProfileItemRepository(project_root)
    items = repo.list()
    if not items:
        return "No profile items yet."
    lines = ["Core profile:"]
    for item in items[:6]:
        lines.append(f"  {item.id}: {item.body[:80]}")
    if len(items) > 6:
        lines.append(f"  ... and {len(items) - 6} more")
    return "\n".join(lines)


def handle_interactive_reflection_command(project_root: Path | None) -> str:
    from nuself.reflection.repository import ReflectionRepository
    from nuself.tui.render import render_reflection_entry_summary

    entries = ReflectionRepository(project_root).list(status="pending")
    if not entries:
        return "No pending reflection ideas."
    lines = ["Pending reflection ideas:"]
    for idx, entry in enumerate(entries):
        lines.extend(indent_lines(render_reflection_entry_summary(entry, index=idx).splitlines(), "  "))
    return "\n".join(lines)


def handle_interactive_inbox_command(project_root: Path | None) -> str:
    sections = [
        handle_interactive_reflection_command(project_root),
        handle_interactive_notify_command(project_root),
    ]
    return "\n\n".join(sections)


def handle_interactive_reflection_list_command(project_root: Path | None) -> str:
    from nuself.reflection.repository import ReflectionRepository
    from nuself.tui.render import render_reflection_entry_summary

    entries = ReflectionRepository(project_root).list()
    if not entries:
        return "No reflection ideas."
    lines = ["All reflection ideas:"]
    for idx, entry in enumerate(entries):
        lines.extend(indent_lines(render_reflection_entry_summary(entry, index=idx).splitlines(), "  "))
    return "\n".join(lines)


def handle_interactive_reflection_show_command(project_root: Path | None, entry_id: str) -> str:
    from nuself.reflection.repository import ReflectionEntryNotFound, ReflectionRepository
    from nuself.tui.render import render_reflection_entry_detail

    try:
        entry = ReflectionRepository(project_root).get(entry_id)
    except ReflectionEntryNotFound:
        return f"Reflection entry not found: {entry_id}"
    return render_reflection_entry_detail(entry)


def handle_interactive_reflection_subcommand(project_root: Path | None, subcmd: str, entry_id: str) -> str:
    from nuself.reflection.repository import ReflectionEntryNotFound, ReflectionRepository

    repo = ReflectionRepository(project_root)
    try:
        repo.get(entry_id)
    except ReflectionEntryNotFound:
        return f"Reflection entry not found: {entry_id}"
    if subcmd == "dismiss":
        repo.dismiss(entry_id)
        return f"Dismissed: {entry_id}"
    if subcmd == "archive":
        repo.archive(entry_id)
        return f"Archived: {entry_id}"
    if subcmd == "promote":
        from nuself.reflection.service import ReflectionService

        try:
            thread = ReflectionService(project_root, repository=repo).promote_to_reason(entry_id)
        except RuntimeError as exc:
            return f"Error: {exc}"
        return f"Promoted reflection to reason thread: {thread.id}\n{render_reason_detail(thread)}"
    return f"Unknown :inbox reflection subcommand: {subcmd}"


def handle_interactive_notify_command(project_root: Path | None) -> str:
    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    entries = NotificationOutbox(project_root).list(status="pending")
    if not entries:
        return "No pending notifications."
    lines = ["Pending notifications:"]
    for index, entry in enumerate(entries):
        lines.append("  " + render_outbox_summary(entry, index=index))
    return "\n".join(lines)


def handle_interactive_notify_list_command(project_root: Path | None) -> str:
    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    entries = NotificationOutbox(project_root).list()
    if not entries:
        return "No notifications."
    lines = ["All notifications:"]
    for index, entry in enumerate(entries):
        lines.append("  " + render_outbox_summary(entry, index=index))
    return "\n".join(lines)


def handle_interactive_notify_show_command(project_root: Path | None, entry_id: str) -> str:
    from nuself.notification import NotificationOutbox, OutboxEntryNotFound
    from nuself.tui.render import render_outbox_detail

    try:
        entry = NotificationOutbox(project_root).get(entry_id)
    except OutboxEntryNotFound:
        return f"Outbox entry not found: {entry_id}"
    return render_outbox_detail(entry)


def handle_interactive_notify_subcommand(project_root: Path | None, subcmd: str, entry_id: str) -> str:
    from nuself.notification import NotificationOutbox, LogOnlyNotificationAdapter, OutboxEntryNotFound

    outbox = NotificationOutbox(project_root)
    try:
        entry = outbox.get(entry_id)
    except OutboxEntryNotFound:
        return f"Outbox entry not found: {entry_id}"
    if subcmd == "send":
        adapter = LogOnlyNotificationAdapter(project_root)
        if adapter.send(entry):
            outbox.mark_sent(entry_id)
            return f"Sent: {entry_id}"
        outbox.mark_failed(entry_id)
        return f"Failed to send: {entry_id}"
    if subcmd == "dismiss":
        outbox.dismiss(entry_id)
        return f"Dismissed: {entry_id}"
    return f"Unknown :inbox notify subcommand: {subcmd}"


def handle_interactive_watch_command(project_root: Path | None) -> None:
    import time

    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    outbox = NotificationOutbox(project_root)
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


def handle_interactive_threads_command(project_root: Path | None) -> str:
    store = ThreadStore(project_root)
    ids = store.list()
    if not ids:
        return "No active threads."
    return "Active threads:\n" + "\n".join(f"  {tid}" for tid in ids)
