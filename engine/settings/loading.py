"""Turn raw (stored or lobby) settings dicts into a validated ``GameSettings``."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from .migrations import migrate
from .models import GameSettings

__all__ = ["parse_settings", "merge_overrides"]


def _group_type(model_cls: type[BaseModel], key: str) -> type[BaseModel] | None:
    field = model_cls.model_fields.get(key)
    annotation = field.annotation if field is not None else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def merge_overrides(
    base: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
    model_cls: type[BaseModel] = GameSettings,
) -> dict[str, Any]:
    """Deep-merge ``overrides`` into ``base`` following the settings groups.

    Groups (nested settings models) merge key by key; every other value,
    including mapping-valued settings such as a cost, is replaced as a whole.
    """
    merged = copy.deepcopy(dict(base))
    for key, value in (overrides or {}).items():
        group = _group_type(model_cls, key)
        if group is not None and isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = merge_overrides(merged[key], value, group)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def parse_settings(raw: Mapping[str, Any], *, implemented_stage: int | None = None) -> GameSettings:
    """Migrate ``raw`` to the current schema version and validate it.

    ``implemented_stage`` overrides ``IMPLEMENTED_STAGE`` (tests, future stages).
    """
    context = None if implemented_stage is None else {"implemented_stage": implemented_stage}
    return GameSettings.model_validate(migrate(raw), context=context)
