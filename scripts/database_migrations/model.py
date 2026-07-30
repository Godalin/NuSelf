"""Contracts and planning for explicit database migration scripts."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

MigrationOperation = Callable[[sqlite3.Connection], None]


class Direction(StrEnum):
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"


@dataclass(frozen=True)
class Migration:
    migration_id: str
    from_version: int
    to_version: int
    upgrade: MigrationOperation
    downgrade: MigrationOperation | None


@dataclass(frozen=True)
class Step:
    migration: Migration
    direction: Direction

    @property
    def destination_version(self) -> int:
        if self.direction is Direction.UPGRADE:
            return self.migration.to_version
        return self.migration.from_version


@dataclass(frozen=True)
class Plan:
    current_version: int
    target_version: int
    steps: tuple[Step, ...]


class RegistryError(ValueError):
    pass


class PathError(ValueError):
    pass


def validate_registry(
    migrations: tuple[Migration, ...],
    *,
    current_version: int,
) -> None:
    identifiers = [migration.migration_id for migration in migrations]
    edges = [
        (migration.from_version, migration.to_version)
        for migration in migrations
    ]
    expected = [(version, version + 1) for version in range(1, current_version)]
    if any(not identifier.strip() for identifier in identifiers):
        raise RegistryError("migration ID must not be blank")
    if len(set(identifiers)) != len(identifiers):
        raise RegistryError("migration IDs must be unique")
    if len(set(edges)) != len(edges):
        raise RegistryError("migration edges must be unique")
    if sorted(edges) != expected:
        raise RegistryError(
            "registry must contain exactly one contiguous adjacent edge "
            "for every supported version"
        )


def plan(
    migrations: tuple[Migration, ...],
    *,
    current_version: int,
    target_version: int,
    supported_version: int,
) -> Plan:
    validate_registry(migrations, current_version=supported_version)
    if current_version not in range(1, supported_version + 1):
        raise PathError(f"unsupported current version: {current_version}")
    if target_version not in range(1, supported_version + 1):
        raise PathError(f"unsupported target version: {target_version}")
    by_source = {migration.from_version: migration for migration in migrations}
    if target_version >= current_version:
        steps = tuple(
            Step(by_source[version], Direction.UPGRADE)
            for version in range(current_version, target_version)
        )
        return Plan(current_version, target_version, steps)
    result: list[Step] = []
    for version in range(current_version - 1, target_version - 1, -1):
        migration = by_source[version]
        if migration.downgrade is None:
            raise PathError(
                f"{migration.migration_id} is a historical forward-only migration"
            )
        result.append(Step(migration, Direction.DOWNGRADE))
    return Plan(current_version, target_version, tuple(result))
