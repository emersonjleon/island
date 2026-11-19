"""Form data that shows a game's current settings in the custom-game form (to edit them)."""
from typing import Any

from engine.settings import load_preset

from .forms import KNOB_PATHS
from .presets import CUSTOM, KNOBS, base_presets
from .settings_editor import all_settings


def settings_form_data(preset: str, overrides: dict[str, Any]) -> dict[str, str]:
    """POST-like data for ``CreateGameForm`` that reproduces ``preset`` + ``overrides``
    as a custom game: changed quick rules and settings filled in, the rest blank."""
    base = preset if preset in base_presets() else "classic"
    current = load_preset(preset, overrides)
    players = current.players.max
    start = load_preset(base, {"players": {"max": players}}, players=players)
    data = {"preset": CUSTOM, "base": base, "max_players": str(players)}
    for knob in KNOBS:
        value, original = knob.read(current), knob.read(start)
        if knob.boolean:
            if value:
                data[knob.name] = "on"
        elif value != original:
            data[knob.name] = str(value)
    for setting in all_settings():
        if setting.path in KNOB_PATHS:
            continue
        value, original = setting.read(current), setting.read(start)
        if value == original:
            continue
        if setting.kind == "map":
            for key, _label in setting.keys:
                if (value or {}).get(key, 0) != (original or {}).get(key, 0):
                    data[setting.key_name(key)] = setting.input_value(value, key)
        else:
            data[setting.name] = setting.input_value(value)
    return data
