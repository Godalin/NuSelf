"""One-shot curator recovery plan command handlers."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.composition import compose_cli_application
from nuself.memory.curator_plan import (
    MemoryCuratorPlanCorruptError,
    MemoryCuratorPlanLockContended,
    MemoryCuratorPlanNotFound,
)
from nuself.runtime.diagnostics import diagnostic_exception_message


def handle_memory_plan_show(args: argparse.Namespace) -> int:
    store = compose_cli_application(args.project_root).memory.curator_plans
    try:
        plan = store.get(args.conversation_id)
    except (MemoryCuratorPlanCorruptError, ValueError) as exc:
        print(
            "Curator plan unavailable: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    if plan is None:
        print(
            f"Curator plan not found for conversation: {args.conversation_id}",
            file=sys.stderr,
        )
        return 1
    print(
        "Curator plan: "
        f"conversation={plan.conversation_id} "
        f"source={plan.source_start}-{plan.source_end} "
        f"observed_at={plan.observed_at} "
        f"actions={len(plan.actions)}"
    )
    for index, action in enumerate(plan.actions):
        target = action.entry_id or "-"
        print(
            f"[{index}] action={action.action} "
            f"type={action.type} "
            f"candidate_id={plan.candidate_id(index)} "
            f"target={target}"
        )
    return 0


def handle_memory_plan_discard(args: argparse.Namespace) -> int:
    if not args.force:
        print(
            "Discarding a curator plan requires --force.",
            file=sys.stderr,
        )
        return 1
    store = compose_cli_application(args.project_root).memory.curator_plans
    try:
        store.discard(args.conversation_id)
    except MemoryCuratorPlanLockContended:
        print(
            "Curator plan is busy for conversation: "
            f"{args.conversation_id}; no plan was discarded.",
            file=sys.stderr,
        )
        return 1
    except MemoryCuratorPlanNotFound:
        print(
            f"Curator plan not found for conversation: {args.conversation_id}",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(
            "Curator plan unavailable: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(
        f"Discarded curator plan for conversation {args.conversation_id}. "
        "Cursor and candidates were not changed."
    )
    return 0
