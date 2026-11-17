"""Named presets: JSON files in this package holding only differences from the defaults."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from importlib import resources
from typing import Any

from ..loading import merge_overrides, parse_settings
from ..models import GameSettings, PlayersSettings
from ..scaling import scale_for_players

__all__ = ["UnknownPresetError", "available_presets", "preset_overrides", "load_preset"]

_NAME = re.compile(r"^[a-z0-9_]{1,32}$")


class UnknownPresetError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__("settings.preset.unknown", {"preset": name})
        self.code = "settings.preset.unknown"
        self.params = {"preset": name}


def available_presets() -> list[str]:
    """Names of the bundled presets, sorted."""
    return sorted(p.name[:-5] for p in resources.files(__package__).iterdir() if p.name.endswith(".json"))


def preset_overrides(name: str) -> dict[str, Any]:
    """The raw differences-from-defaults dict stored for preset ``name``."""
    if not _NAME.match(name):
        raise UnknownPresetError(name)
    path = resources.files(__package__).joinpath(f"{name}.json")
    if not path.is_file():
        raise UnknownPresetError(name)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"preset {name!r} must be a JSON object")
    return data


def load_preset(
    name: str = "classic",
    overrides: Mapping[str, Any] | None = None,
    *,
    implemented_stage: int | None = None,
    players: int | None = None,
) -> GameSettings:
    """Preset ``name`` with ``overrides`` deep-merged on top (groups merge, values replace),
    scaled up for ``players`` (default ``players.max``) when that exceeds ``players.sized_for``.
    The preset's own island size and bank are scaled too; values in ``overrides`` are not.

    ``players`` is the real table size at the start of a game: it also becomes
    ``players.max`` (never below ``players.min``), so the settings describe that table.
    """
    raw = merge_overrides(preset_overrides(name), overrides)
    if players is not None:
        group = dict(raw.get("players") or {})
        group["max"] = max(players, int(group.get("min", PlayersSettings.model_fields["min"].default)))
        raw["players"] = group
    raw = scale_for_players(raw, players, explicit=overrides or {})
    raw["preset"] = name
    return parse_settings(raw, implemented_stage=implemented_stage)
