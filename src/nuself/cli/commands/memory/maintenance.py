"""One-shot memory maintenance command handlers."""

from __future__ import annotations

import argparse
import json
import sys
from typing import cast

from nuself.cli.composition import cli_application
from nuself.memory.composition import (
    compose_memory_curator,
    compose_memory_optimizer,
)
from nuself.cli.commands.memory.common import record_memory_trace
from nuself.domain.memory import MemoryEntry
from nuself.memory.optimizer import (
    MemoryOptimizerSettings,
)


def handle_memory_update(args: argparse.Namespace) -> int:
    application = cli_application()
    curator = compose_memory_curator(application)
    pending = application.memory.observations.pending()
    for observation in pending:
        curator.run_once(observation.id)
    print(f"Memory curator: processed_observations={len(pending)}")
    return 0


def handle_memory_optimize(args: argparse.Namespace) -> int:
    settings = MemoryOptimizerSettings(memory_limit=args.limit)
    result = compose_memory_optimizer(
        cli_application(),
        settings=settings,
    ).run_once()
    print(
        f"Memory optimizer: {result.summary()} "
        f"log={result.log_path}"
    )
    return 0


def handle_memory_export(args: argparse.Namespace) -> int:
    entries = cli_application().memory.entries.list()
    data = [entry.to_wire() for entry in entries]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(data)} memory entries to {args.output}")
    return 0


def handle_memory_import(args: argparse.Namespace) -> int:
    if not args.path.exists():
        print(
            f"Import file not found: {args.path}",
            file=sys.stderr,
        )
        return 1
    raw: object = json.loads(
        args.path.read_text(encoding="utf-8")
    )
    if not isinstance(raw, list):
        print(
            "Import file must contain a JSON array of memory "
            "entries.",
            file=sys.stderr,
        )
        return 1
    application = cli_application()
    repository = application.memory.entries
    data = cast(list[object], raw)
    imported = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        entry = MemoryEntry.from_wire(
            cast(dict[str, object], item)
        )
        repository.save(entry)
        record_memory_trace(
            application.trace.recorder,
            args.project_root,
            entry,
            "import",
        )
        imported += 1
    print(
        f"Imported {imported} memory entries from {args.path}"
    )
    return 0
