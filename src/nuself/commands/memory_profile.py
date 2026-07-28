"""One-shot memory profile command handlers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nuself.commands.output import print_ansi, resolve_handle
from nuself.domain.profile import ProfileItem
from nuself.profile.repository import (
    ProfileItemNotFound,
    ProfileItemRepository,
    ProfileSearchFilters,
)
from nuself.tui.memory import render_profile_detail, render_profile_row


def _items_for_list(
    project_root: Path | None,
    *,
    sort_by: str = "updated_at",
) -> list[ProfileItem]:
    items = ProfileItemRepository(project_root).list()
    if sort_by == "importance":
        return sorted(
            items,
            key=lambda item: (
                -item.importance,
                item.updated_at,
                item.id,
            ),
        )
    if sort_by == "type":
        return sorted(
            items,
            key=lambda item: (
                item.type,
                item.updated_at,
                item.id,
            ),
        )
    return items


def _resolve_profile_id(
    args: argparse.Namespace,
) -> str | None:
    return resolve_handle(
        args.profile_id,
        _items_for_list(args.project_root),
        label="profile",
        get_id=lambda item: item.id,
    )


def handle_memory_profile_list(
    args: argparse.Namespace,
) -> int:
    items = _items_for_list(
        args.project_root, sort_by=args.sort_by
    )
    if not items:
        print("No profile items.")
        return 0
    for index, item in enumerate(items):
        print_ansi(render_profile_row(item, index=index))
    return 0


def handle_memory_profile_search(
    args: argparse.Namespace,
) -> int:
    items = ProfileItemRepository(args.project_root).search(
        args.query,
        ProfileSearchFilters(
            type=args.type,
            tag=args.tag,
            observed_from=args.observed_from,
            observed_to=args.observed_to,
            valid_on=args.valid_on,
        ),
    )
    if not items:
        print("No matching profile items.")
        return 0
    for item in items:
        print_ansi(render_profile_row(item))
    return 0


def handle_memory_profile_show(
    args: argparse.Namespace,
) -> int:
    profile_id = _resolve_profile_id(args)
    if profile_id is None:
        return 1
    try:
        item = ProfileItemRepository(args.project_root).get(
            profile_id
        )
    except ProfileItemNotFound:
        print(
            f"Profile item not found: {profile_id}",
            file=sys.stderr,
        )
        return 1
    print_ansi(render_profile_detail(item))
    return 0


def handle_memory_profile_delete(
    args: argparse.Namespace,
) -> int:
    repository = ProfileItemRepository(args.project_root)
    profile_id = _resolve_profile_id(args)
    if profile_id is None:
        return 1
    try:
        repository.delete(profile_id)
    except ProfileItemNotFound:
        print(
            f"Profile item not found: {profile_id}",
            file=sys.stderr,
        )
        return 1
    repository.reindex()
    print(f"Deleted profile item: {profile_id}")
    return 0


def handle_memory_profile_reindex(
    args: argparse.Namespace,
) -> int:
    path = ProfileItemRepository(args.project_root).reindex()
    print(f"Rebuilt profile index: {path}")
    return 0
