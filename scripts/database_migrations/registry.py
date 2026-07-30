"""Complete ordered registry for operator-run migration scripts."""

from scripts.database_migrations import v001_to_v002, v002_to_v003, v003_to_v004
from scripts.database_migrations.model import Migration, Plan, plan, validate_registry

CURRENT_VERSION = 4
MIGRATIONS = (
    Migration("v001_to_v002", 1, 2, v001_to_v002.upgrade, None),
    Migration("v002_to_v003", 2, 3, v002_to_v003.upgrade, None),
    Migration(
        "v003_to_v004",
        3,
        4,
        v003_to_v004.upgrade,
        v003_to_v004.downgrade,
    ),
)
validate_registry(MIGRATIONS, current_version=CURRENT_VERSION)


def migration_plan(current_version: int, target_version: int) -> Plan:
    return plan(
        MIGRATIONS,
        current_version=current_version,
        target_version=target_version,
        supported_version=CURRENT_VERSION,
    )
