"""JSON Schema export of ``GameSettings`` (for the lobby form and the frontend)."""

from __future__ import annotations

from typing import Any

from .enums import LATER_STAGE_VALUES
from .models import CURRENT_SCHEMA_VERSION, IMPLEMENTED_STAGE, GameSettings

__all__ = ["export_json_schema"]


def export_json_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of ``GameSettings``.

    Every property carries ``label`` and ``stage``. Extra top-level keys:
    ``x-implemented-stage``, ``x-schema-version`` and ``x-later-stage-values``
    (``{EnumName: {value: stage}}``).
    """
    schema = GameSettings.model_json_schema(mode="validation")
    later = {enum.__name__: dict(values) for enum, values in LATER_STAGE_VALUES.items()}
    schema["x-implemented-stage"] = IMPLEMENTED_STAGE
    schema["x-schema-version"] = CURRENT_SCHEMA_VERSION
    schema["x-later-stage-values"] = later
    return schema
