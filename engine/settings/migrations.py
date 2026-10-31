"""Upgrade raw settings dicts from older ``schema_version`` values before validation.

``MIGRATIONS[n]`` turns a version-``n`` dict into a version-``n + 1`` dict.
Add a step whenever ``CURRENT_SCHEMA_VERSION`` is bumped.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Any

from .models import CURRENT_SCHEMA_VERSION

__all__ = ["Migration", "MIGRATIONS", "MigrationError", "migrate"]

Migration = Callable[[dict[str, Any]], dict[str, Any]]

MIGRATIONS: dict[int, Migration] = {}
"""from_version -> step to from_version + 1. Empty while only v1 exists."""


class MigrationError(ValueError):
    """Raw settings cannot be brought to the current schema version."""

    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code, params)
        self.code = code
        self.params = params


def migrate(
    raw: Mapping[str, Any],
    *,
    migrations: Mapping[int, Migration] | None = None,
    target: int = CURRENT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Return a migrated deep copy of ``raw``. A missing ``schema_version`` means ``target``."""
    steps = MIGRATIONS if migrations is None else migrations
    data = copy.deepcopy(dict(raw))
    version = data.get("schema_version", target)
    if not isinstance(version, int) or isinstance(version, bool):
        raise MigrationError("settings.migrate.bad_version", version=version)
    if version > target:
        raise MigrationError("settings.migrate.too_new", version=version, target=target)
    while version < target:
        step = steps.get(version)
        if step is None:
            raise MigrationError("settings.migrate.no_step", version=version)
        data = step(data)
        version += 1
        data["schema_version"] = version
    return data
