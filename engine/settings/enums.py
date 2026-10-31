"""Engine enums used by the settings (and by the rest of the engine).

All are ``StrEnum`` so they serialize as plain strings. Values that are only
allowed from a later stage are listed in :data:`LATER_STAGE_VALUES`.
"""

from __future__ import annotations

from enum import Enum, StrEnum

__all__ = [
    "Resource", "Terrain", "TERRAIN_RESOURCE", "PRODUCING_TERRAINS", "BuildKind", "DevCardKind",
    "SeatOrder", "BoardShape", "BoardLayout", "RobberStart", "DiceMode", "StartTrigger",
    "ShortageRule", "ConflictRule", "SetupMode", "MoveOnSeven", "AdjacencyTiming", "Rounding",
    "Landing", "BuilderRequired", "SpawnAt", "MapVisibility", "InfoVisibility",
    "ScoreVisibility", "ProductionLog", "TradeOffers", "Cooldown",
    "STAGE_LATER", "LATER_STAGE_VALUES", "value_stage",
]


class Resource(StrEnum):
    LUMBER = "lumber"
    BRICK = "brick"
    WOOL = "wool"
    GRAIN = "grain"
    ORE = "ore"
    FISH = "fish"


class Terrain(StrEnum):
    FOREST = "forest"
    PASTURE = "pasture"
    FIELDS = "fields"
    HILLS = "hills"
    MOUNTAINS = "mountains"
    DESERT = "desert"


TERRAIN_RESOURCE: dict[Terrain, Resource | None] = {
    Terrain.FOREST: Resource.LUMBER,
    Terrain.PASTURE: Resource.WOOL,
    Terrain.FIELDS: Resource.GRAIN,
    Terrain.HILLS: Resource.BRICK,
    Terrain.MOUNTAINS: Resource.ORE,
    Terrain.DESERT: None,
}
"""Land terrain -> produced resource. Fishing grounds (sea) produce ``Resource.FISH``."""

PRODUCING_TERRAINS: tuple[Terrain, ...] = tuple(t for t, r in TERRAIN_RESOURCE.items() if r is not None)


class BuildKind(StrEnum):
    ROAD = "road"
    SETTLEMENT = "settlement"
    CITY = "city"
    MEGACITY = "megacity"


class DevCardKind(StrEnum):
    KNIGHT = "knight"
    VICTORY_POINT = "victory_point"
    ROAD_BUILDING = "road_building"
    YEAR_OF_PLENTY = "year_of_plenty"
    MONOPOLY = "monopoly"


class SeatOrder(StrEnum):
    RANDOM = "random"
    HOST = "host"


class BoardShape(StrEnum):
    SPIRAL = "spiral"
    HEXAGON = "hexagon"
    CUSTOM = "custom"


class BoardLayout(StrEnum):
    RANDOM = "random"
    SEEDED = "seeded"
    BEGINNER = "beginner"


class RobberStart(StrEnum):
    DESERT = "desert"
    RANDOM_LAND = "random_land"


class DiceMode(StrEnum):
    TWO_DICE = "two_dice"
    DECK = "deck"


class StartTrigger(StrEnum):
    FIRST_SETTLEMENT = "first_settlement"


class ShortageRule(StrEnum):
    CLASSIC = "classic"


class ConflictRule(StrEnum):
    FIRST_TO_FINISH = "first_to_finish"


class SetupMode(StrEnum):
    SETTLERS = "settlers"
    SNAKE_CLICK = "snake_click"
    RANDOM = "random"


class MoveOnSeven(StrEnum):
    RANDOM_NEIGHBOUR = "random_neighbour"
    PLAYER = "player"


class AdjacencyTiming(StrEnum):
    BEFORE_MOVE = "before_move"
    AFTER_MOVE = "after_move"


class Rounding(StrEnum):
    FLOOR = "floor"
    CEIL = "ceil"


class Landing(StrEnum):
    EVEN_COAST = "even_coast"


class BuilderRequired(StrEnum):
    SETUP_ONLY = "setup_only"
    ALWAYS = "always"


class SpawnAt(StrEnum):
    OWN_BUILDING = "own_building"


class MapVisibility(StrEnum):
    OPEN = "open"
    GROWING = "growing"
    EXPLORED = "explored"
    LIVE_FOG = "live_fog"


class InfoVisibility(StrEnum):
    COUNTS = "counts"
    OPEN = "open"
    HIDDEN = "hidden"


class ScoreVisibility(StrEnum):
    SHOWN = "shown"
    HIDDEN_UNTIL_END = "hidden_until_end"


class ProductionLog(StrEnum):
    ALL = "all"
    OWN = "own"


class TradeOffers(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class Cooldown(StrEnum):
    PER_ROLL = "per_roll"
    MS = "ms"


STAGE_LATER = 5
"""Stage number used for features planned after stage 4 ("Later" in the design scope)."""

LATER_STAGE_VALUES: dict[type[Enum], dict[str, int]] = {
    BoardShape: {BoardShape.HEXAGON.value: STAGE_LATER, BoardShape.CUSTOM.value: STAGE_LATER},
    BoardLayout: {BoardLayout.BEGINNER.value: 3},
    DiceMode: {DiceMode.DECK.value: 3},
    SetupMode: {SetupMode.SNAKE_CLICK.value: 3, SetupMode.RANDOM.value: 3},
    MoveOnSeven: {MoveOnSeven.PLAYER.value: 3},
    AdjacencyTiming: {AdjacencyTiming.AFTER_MOVE.value: 3},
    Rounding: {Rounding.CEIL.value: 3},
    BuilderRequired: {BuilderRequired.ALWAYS.value: 3},
    MapVisibility: {MapVisibility.GROWING.value: 3, MapVisibility.EXPLORED.value: 3,
                    MapVisibility.LIVE_FOG.value: 3},
    ScoreVisibility: {ScoreVisibility.HIDDEN_UNTIL_END.value: 3},
    TradeOffers: {TradeOffers.PRIVATE.value: 3},
}
"""Enum type -> {value: stage} for values arriving later than the field holding them.

Keyed by type because ``StrEnum`` members of different enums with the same
text (e.g. ``SeatOrder.RANDOM`` and ``SetupMode.RANDOM``) are equal and hash alike.
"""


def value_stage(value: Enum) -> int:
    """Stage at which an enum value becomes available (1 unless listed above)."""
    return LATER_STAGE_VALUES.get(type(value), {}).get(value.value, 1)
