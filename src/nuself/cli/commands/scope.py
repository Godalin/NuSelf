"""Scope initialization and path-inspection commands."""

from __future__ import annotations

import argparse

from nuself.config import ConfigSystem
from nuself.layout_migration import migrate_legacy_layout
from nuself.private_fs import ensure_managed_directory
from nuself.scope import NuSelfScope, resolve_runtime_paths, resolve_scope
from nuself.storage import get_default_backend


def handle_init(args: argparse.Namespace) -> int:
    scope = _scope(args)
    paths = resolve_runtime_paths(scope)
    for directory in (
        paths.authority_root,
        paths.sources_dir,
        paths.logs_dir,
        paths.exports_dir,
        paths.imports_dir,
        paths.runtime_dir,
    ):
        ensure_managed_directory(paths.authority_root, directory)
    get_default_backend(paths.authority_root)
    print(
        f"Initialized NuSelf {scope.kind} authority: "
        f"{paths.authority_root}"
    )
    return 0


def handle_dev_paths(args: argparse.Namespace) -> int:
    scope = _scope(args)
    paths = resolve_runtime_paths(scope)
    config_layers = [paths.user_config_file]
    if paths.config_file != paths.user_config_file:
        config_layers.append(paths.config_file)

    print(f"scope: {scope.kind}")
    print(f"authority_id: {scope.authority_id}")
    print(f"authority_root: {paths.authority_root}")
    if scope.workspace_root is not None:
        print(f"workspace_root: {scope.workspace_root}")
    print("config_layers:")
    for path in config_layers:
        state = "found" if path.is_file() else "missing"
        print(f"  - {path} ({state})")
    print(f"database: {paths.database_file}")
    print(f"sources: {paths.sources_dir}")
    print(f"logs: {paths.logs_dir}")
    print(f"exports: {paths.exports_dir}")
    print(f"imports: {paths.imports_dir}")
    print(f"runtime: {paths.runtime_dir}")
    print(f"socket_runtime: {paths.socket_runtime_dir}")
    print(f"socket: {paths.socket_path}")
    return 0


def handle_dev_config(args: argparse.Namespace) -> int:
    scope = _scope(args)
    paths = resolve_runtime_paths(scope)
    handle_dev_paths(args)
    print("daemon_reload: restart required after configuration changes")
    print("config_effective:")
    effective = ConfigSystem.load_scope(scope)
    for key, value in sorted(
        ConfigSystem().as_flat_dict(effective).items()
    ):
        print(f"  {key}: {value}")
    print(f"selected_config: {paths.config_file}")
    return 0


def handle_migrate_layout(args: argparse.Namespace) -> int:
    target_scope = resolve_scope(
        local=args.to_local,
        workspace=args.migration_workspace,
    )
    target = migrate_legacy_layout(args.source, target_scope)
    print(
        f"Migrated legacy layout to {target_scope.kind} authority: "
        f"{target}"
    )
    print(f"Source preserved: {args.source.expanduser().absolute()}")
    return 0


def _scope(args: argparse.Namespace) -> NuSelfScope:
    scope = getattr(args, "scope", None)
    if not isinstance(scope, NuSelfScope):
        raise TypeError("CLI scope was not resolved before dispatch")
    return scope
