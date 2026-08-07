"""Side-effect-free command readiness and failure disposition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import cast

import yaml

from nuself.cli.exit_codes import CliExitCode
from nuself.config.scope import NuSelfScope, resolve_runtime_paths


class AuthorityRequirement(str, Enum):
    NONE = "none"
    INITIALIZED = "initialized"


class ModelRequirement(str, Enum):
    NONE = "none"
    USABLE = "usable"


@dataclass(frozen=True)
class CommandRequirements:
    authority: AuthorityRequirement = AuthorityRequirement.INITIALIZED
    model: ModelRequirement = ModelRequirement.NONE
    allow_message_without_model: bool = False


NO_READINESS = CommandRequirements(
    authority=AuthorityRequirement.NONE,
)
INITIALIZED_AUTHORITY = CommandRequirements()
MODEL_READY = CommandRequirements(model=ModelRequirement.USABLE)
INTERACTIVE_MODEL_READY = CommandRequirements(
    model=ModelRequirement.USABLE,
    allow_message_without_model=True,
)


@dataclass(frozen=True)
class ReadinessFailure:
    code: str
    message: str
    action: str
    exit_code: CliExitCode = CliExitCode.SETUP_REQUIRED

    def render(self) -> str:
        return f"{self.message}\n\nRun:\n  {self.action}"


def inspect_command_readiness(
    scope: NuSelfScope,
    requirements: CommandRequirements,
    *,
    message: object = None,
) -> ReadinessFailure | None:
    """Inspect prerequisites without creating or hardening managed state."""

    paths = resolve_runtime_paths(scope)
    if requirements.authority is AuthorityRequirement.INITIALIZED:
        database = paths.database_file
        if (
            database.is_symlink()
            or not database.exists()
            or not database.is_file()
        ):
            return ReadinessFailure(
                code="authority-not-initialized",
                message=(
                    f"NuSelf is not initialized for the selected "
                    f"{scope.kind} authority:\n  {paths.authority_root}"
                ),
                action=_scoped_command(scope, "init"),
            )
    model_required = (
        requirements.model is ModelRequirement.USABLE
        and not (
            requirements.allow_message_without_model
            and isinstance(message, str)
            and bool(message.strip())
        )
    )
    if model_required:
        try:
            usable = _has_usable_model(scope)
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError):
            return ReadinessFailure(
                code="configuration-invalid",
                message=(
                    "The selected NuSelf configuration is invalid or "
                    f"unreadable:\n  {paths.config_file}"
                ),
                action=_edit_command(paths.config_file),
            )
        if not usable:
            return ReadinessFailure(
                code="model-not-configured",
                message=(
                    "No usable model endpoint is configured for the selected "
                    f"{scope.kind} authority:\n  {paths.config_file}"
                ),
                action=_edit_command(paths.config_file),
            )
    return None


def _has_usable_model(scope: NuSelfScope) -> bool:
    paths = resolve_runtime_paths(scope)
    layers = [paths.user_config_file]
    if paths.config_file != paths.user_config_file:
        layers.append(paths.config_file)
    endpoints: object = None
    for path in layers:
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("configuration path is not a regular file")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise ValueError("configuration root must be an object")
        mapping = cast(dict[object, object], raw)
        if "llm" in mapping:
            endpoints = mapping["llm"]
    if not isinstance(endpoints, list):
        return False
    endpoint_values = cast(list[object], endpoints)
    return any(
        _usable_endpoint(endpoint)
        for endpoint in endpoint_values
    )


def _usable_endpoint(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    endpoint = cast(dict[object, object], value)
    return (
        _non_blank(endpoint.get("api_key"))
        and _non_blank(endpoint.get("model"))
        and (
            _non_blank(endpoint.get("base_url"))
            or endpoint.get("anthropic") is True
        )
    )


def _non_blank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _scoped_command(scope: NuSelfScope, command: str) -> str:
    if scope.kind == "workspace":
        if scope.workspace_root == Path.cwd().absolute():
            return f"nuself --local {command}"
        return f"nuself --workspace {scope.workspace_root} {command}"
    return f"nuself {command}"


def _edit_command(path: Path) -> str:
    return f'${{EDITOR:-vi}} "{path}"'
