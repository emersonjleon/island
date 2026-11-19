"""JSON Schema export of ``GameSettings`` (for the lobby form and the frontend)."""

from __future__ import annotations

from typing import Any

from .enums import LATER_STAGE_VALUES
from .models import CURRENT_SCHEMA_VERSION, EARLY_FEATURES, IMPLEMENTED_STAGE, GameSettings

__all__ = ["export_json_schema"]


def export_json_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of ``GameSettings``.

    Every property carries ``label`` and ``stage``. Extra top-level keys:
    ``x-implemented-stage``, ``x-schema-version``, ``x-later-stage-values``
    (``{EnumName: {value: stage}}``) and ``x-early-features`` (later-stage settings
    ``path`` and values ``path=value`` already available).
    """
    schema = GameSettings.model_json_schema(mode="validation")
    later = {enum.__name__: dict(values) for enum, values in LATER_STAGE_VALUES.items()}
    schema["x-implemented-stage"] = IMPLEMENTED_STAGE
    schema["x-schema-version"] = CURRENT_SCHEMA_VERSION
    schema["x-later-stage-values"] = later
    schema["x-early-features"] = sorted(EARLY_FEATURES)
    return schema
