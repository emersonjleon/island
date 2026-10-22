"""Per-game settings: every game number lives here, with its default.

Typical use::

    from engine.settings import GameSettings, load_preset, parse_settings, resolve_board_counts

    settings = load_preset("classic", {"board": {"land_hexes": 37}})
    counts = resolve_board_counts(settings)
"""

from .enums import (
    LATER_STAGE_VALUES, PRODUCING_TERRAINS, STAGE_LATER, TERRAIN_RESOURCE, AdjacencyTiming, BoardLayout,
    BoardShape, BuilderRequired, BuildKind, ConflictRule, Cooldown, DevCardKind, DiceMode, InfoVisibility,
    Landing, MapVisibility, MoveOnSeven, ProductionLog, Resource, RobberStart, Rounding, ScoreVisibility,
    SeatOrder, SetupMode, ShortageRule, SpawnAt, StartTrigger, Terrain, TradeOffers, value_stage,
)
from .loading import merge_overrides, parse_settings
from .migrations import MIGRATIONS, MigrationError, migrate
from .models import (
    CURRENT_SCHEMA_VERSION, IMPLEMENTED_STAGE, BankSettings, BoardSettings, BuildSettings,
    BuildTimeSettings, ClockSettings, CostSettings, DevCardSettings, EconomySettings,
    FishingGroundSettings, GameSettings, HarborSettings, LargestArmySettings, LongestRoadSettings,
    PieceSettings, PlayersSettings, ProductionSettings, RobberSettings, SettlerSettings, SetupSettings,
    SightSettings, StartingResourcesSettings, TradeRatioSettings, TradingSettings, VictorySettings,
    VisibilitySettings, stage_violations,
)
from .presets import UnknownPresetError, available_presets, load_preset, preset_overrides
from .resolve import (
    STANDARD_FISHING_GROUNDS, STANDARD_GENERIC_HARBORS, STANDARD_LAND_HEXES, STANDARD_NUMBER_TOKENS,
    STANDARD_TERRAIN_COUNTS, ResolvedBoardCounts, resolve_board_counts, scale_counts, scale_round,
)
from .schema import export_json_schema

__all__ = [
    # enums
    "Resource", "Terrain", "TERRAIN_RESOURCE", "PRODUCING_TERRAINS", "BuildKind", "DevCardKind",
    "SeatOrder", "BoardShape", "BoardLayout", "RobberStart", "DiceMode", "StartTrigger", "ShortageRule",
    "ConflictRule", "SetupMode", "MoveOnSeven", "AdjacencyTiming", "Rounding", "Landing",
    "BuilderRequired", "SpawnAt", "MapVisibility", "InfoVisibility", "ScoreVisibility", "ProductionLog",
    "TradeOffers", "Cooldown", "STAGE_LATER", "LATER_STAGE_VALUES", "value_stage",
    # models
    "IMPLEMENTED_STAGE", "CURRENT_SCHEMA_VERSION", "GameSettings", "PlayersSettings", "BoardSettings",
    "FishingGroundSettings", "HarborSettings", "ClockSettings", "EconomySettings", "CostSettings",
    "ProductionSettings", "StartingResourcesSettings", "BankSettings", "TradeRatioSettings",
    "PieceSettings", "BuildSettings", "BuildTimeSettings", "SetupSettings", "RobberSettings",
    "SettlerSettings", "VisibilitySettings", "SightSettings", "VictorySettings", "LongestRoadSettings",
    "LargestArmySettings", "TradingSettings", "DevCardSettings", "stage_violations",
    # resolution
    "ResolvedBoardCounts", "resolve_board_counts", "scale_counts", "scale_round", "STANDARD_LAND_HEXES",
    "STANDARD_TERRAIN_COUNTS", "STANDARD_NUMBER_TOKENS", "STANDARD_FISHING_GROUNDS",
    "STANDARD_GENERIC_HARBORS",
    # loading
    "parse_settings", "merge_overrides", "migrate", "MIGRATIONS", "MigrationError",
    "load_preset", "available_presets", "preset_overrides", "UnknownPresetError",
    "export_json_schema",
]
