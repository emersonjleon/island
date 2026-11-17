"""The game types offered when creating a game, and the settings a host may change.

Each game type is an engine preset (``engine/settings/presets``). The lobby shows a
short summary of each one ("stats") for every table size, and the "custom" type
lets the host change the settings listed in ``KNOBS``.
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.utils.translation import gettext, gettext_lazy as _

from engine.settings import GameSettings, Resource, available_presets, load_preset

CUSTOM = "custom"
MS_PER_SECOND = 1000
MIN_TABLE = 2
MAX_TABLE = 12

# Shown in this order; presets not listed here follow, under their own name.
PRESET_INFO = {
    "blitz": (_("Blitz"), _("Fast dice, quicker builds and fewer points to win.")),
    "classic": (_("Classic"), _("The standard island for 3 or 4 players.")),
    "expanded": (_("Expanded"), _("A bigger island, bank and set of pieces for 5 or 6 players, and more points to win.")),
    "huge": (_("Huge"), _("A very big island for 7 or more players, and a long game.")),
    CUSTOM: (_("Custom"), _("Start from Classic and choose the rules yourself.")),
}


def preset_names() -> list[str]:
    bundled = available_presets()
    return [p for p in PRESET_INFO if p in bundled] + [p for p in bundled if p not in PRESET_INFO]


def preset_label(name: str):
    return PRESET_INFO[name][0] if name in PRESET_INFO else name.replace("_", " ").title()


def preset_description(name: str):
    return PRESET_INFO[name][1] if name in PRESET_INFO else ""


# ------------------------------------------------------------------ knobs
@dataclass(frozen=True)
class Knob:
    """One setting the host can change in a custom game.

    ``path`` is where it lives in the settings; the form shows the value divided by
    ``factor`` (milliseconds as seconds). ``per_resource`` knobs set one number for
    every resource of a resource map.
    """

    name: str
    path: tuple[str, ...]
    group: str
    label: Any
    min: int = 0
    max: int = 0
    factor: int = 1
    boolean: bool = False
    per_resource: bool = False
    help: Any = ""

    def read(self, settings: GameSettings) -> int | bool:
        value: Any = settings
        for part in self.path:
            value = getattr(value, part)
        if self.per_resource:
            value = min(value[r] for r in Resource)
        if self.boolean:
            return bool(value)
        return int(value) // self.factor

    def override(self, value: int | bool) -> dict[str, Any]:
        """The overrides dict that sets this knob to ``value``."""
        leaf: Any = bool(value) if self.boolean else int(value) * self.factor
        if self.per_resource:
            leaf = {r.value: leaf for r in Resource}
        for part in reversed(self.path):
            leaf = {part: leaf}
        return leaf


GROUPS = [
    ("island", _("Island")),
    ("pace", _("Pace")),
    ("economy", _("Bank and trade")),
    ("pieces", _("Pieces per player")),
    ("robber", _("Robber")),
    ("victory", _("Victory")),
]

KNOBS = [
    Knob("land_hexes", ("board", "land_hexes"), "island", _("Island size (land hexes)"), 7, 250,
         help=_("Blank grows the island with the number of players.")),
    Knob("red_may_touch", ("board", "red_may_touch"), "island", _("6 and 8 may be next to each other"), boolean=True),
    Knob("harbor_ratio", ("board", "harbors", "generic_ratio"), "island", _("Generic harbor trade (cards for 1)"), 1, 10),
    Knob("special_harbor_ratio", ("board", "harbors", "specific_ratio"), "island",
         _("Special harbor trade (cards for 1)"), 1, 10),
    Knob("roll_interval", ("clock", "roll_interval_ms"), "pace", _("Seconds between dice rolls"), 5, 120,
         factor=MS_PER_SECOND),
    Knob("road_time", ("build", "time_ms", "road"), "pace", _("Seconds to build a road"), 0, 600,
         factor=MS_PER_SECOND),
    Knob("settlement_time", ("build", "time_ms", "settlement"), "pace", _("Seconds to build a settlement"), 0, 600,
         factor=MS_PER_SECOND),
    Knob("city_time", ("build", "time_ms", "city"), "pace", _("Seconds to build a city"), 0, 600,
         factor=MS_PER_SECOND),
    Knob("bank_cards", ("economy", "bank", "per_resource"), "economy", _("Bank cards of each resource"), 0, 1000,
         per_resource=True, help=_("Blank grows the bank with the number of players.")),
    Knob("bank_ratio", ("economy", "trade", "bank_ratio"), "economy", _("Bank trade (cards for 1)"), 1, 10),
    Knob("settlement_yield", ("economy", "production_per", "settlement"), "economy",
         _("Resources a settlement produces"), 0, 10),
    Knob("city_yield", ("economy", "production_per", "city"), "economy", _("Resources a city produces"), 0, 10),
    Knob("roads", ("pieces", "roads"), "pieces", _("Roads"), 0, 200),
    Knob("settlements", ("pieces", "settlements"), "pieces", _("Settlements"), 1, 100),
    Knob("cities", ("pieces", "cities"), "pieces", _("Cities"), 0, 100),
    Knob("robber", ("robber", "enabled"), "robber", _("Robber on a 7"), boolean=True),
    Knob("card_limit", ("robber", "card_limit"), "robber", _("Safe hand size on a 7"), 0, 100,
         help=_("Players holding more cards than this lose some on a 7.")),
    Knob("steal_pct", ("robber", "steal_pct"), "robber", _("Share of the hand lost on a 7 (%)"), 0, 100),
    Knob("spare_setup", ("robber", "spare_setup"), "robber",
         _("Spare players still placing their first settlements"), boolean=True),
    Knob("target", ("victory", "target"), "victory", _("Points to win"), 5, 20),
]
KNOBS_BY_NAME = {k.name: k for k in KNOBS}

# The summary shown for every game type: (label, knob names joined with " / ").
STATS = [
    (_("Island size (land hexes)"), ("land_hexes",)),
    (_("Points to win"), ("target",)),
    (_("Seconds between dice rolls"), ("roll_interval",)),
    (_("Bank cards of each resource"), ("bank_cards",)),
    (_("Roads / settlements / cities"), ("roads", "settlements", "cities")),
    (_("Seconds to build a road / settlement / city"), ("road_time", "settlement_time", "city_time")),
    (_("Bank trade (cards for 1)"), ("bank_ratio",)),
    (_("Robber on a 7"), ("robber",)),
]


@lru_cache(maxsize=None)
def preset_values(name: str, players: int) -> dict[str, int | bool]:
    """Every knob's value in preset ``name`` for a full table of ``players``."""
    settings = load_preset(name, {"players": {"max": players}}, players=players)
    return {k.name: k.read(settings) for k in KNOBS}


def default_players(name: str) -> int:
    return load_preset(name).players.max


def presets_data() -> dict[str, Any]:
    """Everything the create-game page needs to show live summaries (JSON-ready)."""
    return {
        "presets": {
            name: {
                "players": default_players(name),
                "values": {n: preset_values(name, n) for n in range(MIN_TABLE, MAX_TABLE + 1)},
            }
            for name in preset_names()
        },
        "stats": [{"label": str(label), "knobs": list(knobs)} for label, knobs in STATS],
        "custom": CUSTOM,
    }


def show(value: int | bool) -> str:
    if isinstance(value, bool):
        return gettext("Yes") if value else gettext("No")
    return str(value)


def stats_rows(values: dict[str, int | bool]) -> list[tuple[Any, str]]:
    """``STATS`` filled in with ``values``, as (label, text) for templates."""
    return [(label, " / ".join(show(values[k]) for k in knobs)) for label, knobs in STATS]


def settings_values(settings: GameSettings) -> dict[str, int | bool]:
    return {k.name: k.read(settings) for k in KNOBS}
