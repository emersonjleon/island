"""``GameSettings``: every game number, with its default, bounds and stage.

Each field carries ``json_schema_extra={"label": "settings.<path>", "stage": N}``.
``stage`` is the design stage in which the feature arrives. A root validator
rejects non-default values of fields (and enum values) from stages above the
implemented stage; see :func:`stage_violations`.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import Enum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError, PydanticUndefined

from .enums import (
    AdjacencyTiming, BoardLayout, BoardShape, BuilderRequired, ConflictRule, Cooldown, DevCardKind,
    DiceMode, InfoVisibility, Landing, MapVisibility, MoveOnSeven, ProductionLog, Resource, Rounding,
    RobberStart, ScoreVisibility, SeatOrder, SetupMode, ShortageRule, SpawnAt, StartTrigger, Terrain,
    TradeOffers, value_stage,
)
from .resolve import STANDARD_NUMBER_TOKENS, resolve_board_counts

__all__ = [
    "IMPLEMENTED_STAGE", "CURRENT_SCHEMA_VERSION", "GameSettings", "stage_violations",
    "PlayersSettings", "BoardSettings", "FishingGroundSettings", "HarborSettings", "ClockSettings",
    "EconomySettings", "CostSettings", "ProductionSettings", "StartingResourcesSettings",
    "BankSettings", "TradeRatioSettings", "PieceSettings", "BuildSettings", "BuildTimeSettings",
    "SetupSettings", "RobberSettings", "SettlerSettings", "VisibilitySettings", "SightSettings",
    "VictorySettings", "LongestRoadSettings", "LargestArmySettings", "TradingSettings", "DevCardSettings",
]

IMPLEMENTED_STAGE = 1
"""Highest design stage the engine implements. Context key ``implemented_stage`` overrides it."""

CURRENT_SCHEMA_VERSION = 1

_MAX_MS = 3_600_000
_MAX_COUNT = 1000

Count = Annotated[int, Field(ge=0, le=_MAX_COUNT)]
"""Non-negative bounded int used in resource / piece / card maps."""
Token = Annotated[int, Field(ge=1, le=80)]
"""A number-token value; checked against the dice range in ``GameSettings``."""
ResourceMap = dict[Resource, Count]


def setting(
    default: Any = PydanticUndefined,
    *,
    label: str,
    stage: int = 1,
    factory: Any = None,
    later_stage_above: tuple[int, int] | None = None,
    **constraints: Any,
) -> Any:
    """``Field`` with the label/stage metadata every setting needs.

    ``later_stage_above=(limit, stage)``: values greater than ``limit`` need ``stage``.
    """
    extra: dict[str, Any] = {"label": label, "stage": stage}
    if later_stage_above is not None:
        extra["later_stage_above"] = {"value": later_stage_above[0], "stage": later_stage_above[1]}
    if factory is not None:
        return Field(default_factory=factory, json_schema_extra=extra, **constraints)
    return Field(default, json_schema_extra=extra, **constraints)


def _error(code: str, message: str, **params: Any) -> PydanticCustomError:
    return PydanticCustomError(code, message, params)


class _Group(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)


# --------------------------------------------------------------------- players
class PlayersSettings(_Group):
    min: int = setting(2, label="settings.players.min", ge=2, le=6, later_stage_above=(4, 3))
    max: int = setting(4, label="settings.players.max", ge=2, le=6, later_stage_above=(4, 3))
    seat_order: SeatOrder = setting(SeatOrder.RANDOM, label="settings.players.seat_order")

    @model_validator(mode="after")
    def _min_le_max(self) -> Self:
        if self.min > self.max:
            raise _error("settings.players.min_gt_max", "players.min ({min}) > players.max ({max})",
                         min=self.min, max=self.max)
        return self


# ----------------------------------------------------------------------- board
class FishingGroundSettings(_Group):
    count: int | None = setting(None, label="settings.board.fishing_grounds.count", ge=0, le=250)
    """None = auto (6 at 19 land hexes, scaled)."""
    tokens: tuple[Token, ...] = setting((4, 5, 6, 8, 9, 10), label="settings.board.fishing_grounds.tokens",
                                        max_length=250)
    """Token values, cycled in order when the count differs from their number."""
    min_gap: int = setting(1, label="settings.board.fishing_grounds.min_gap", ge=0, le=5)
    """Minimum number of hexes between two fishing grounds."""

    @model_validator(mode="after")
    def _tokens_present(self) -> Self:
        if not self.tokens and self.count != 0:
            raise _error("settings.board.fishing_tokens_empty", "fishing_grounds.tokens is empty")
        return self


class HarborSettings(_Group):
    generic: int | None = setting(None, label="settings.board.harbors.generic", ge=0, le=250)
    """Generic (3:1) harbors. None = auto (4 at 19 land hexes, scaled)."""
    specific: dict[Resource, Annotated[int, Field(ge=0, le=50)]] = setting(
        {Resource.LUMBER: 1, Resource.WOOL: 1, Resource.GRAIN: 1, Resource.BRICK: 1, Resource.ORE: 1,
         Resource.FISH: 0},
        label="settings.board.harbors.specific")
    """Resource-specific (2:1) harbors per resource; never auto-scaled; missing = 0."""
    generic_ratio: int = setting(3, label="settings.board.harbors.generic_ratio", ge=1, le=10)
    specific_ratio: int = setting(2, label="settings.board.harbors.specific_ratio", ge=1, le=10)


class BoardSettings(_Group):
    land_hexes: int = setting(19, label="settings.board.land_hexes", ge=7, le=250)
    shape: BoardShape = setting(BoardShape.SPIRAL, label="settings.board.shape")
    layout: BoardLayout = setting(BoardLayout.RANDOM, label="settings.board.layout")
    seed: int | None = setting(None, label="settings.board.seed", ge=0, le=2**63 - 1)
    """Board seed for ``layout=seeded``. None = derived from the game seed."""
    terrain_counts: dict[Terrain, Annotated[int, Field(ge=0, le=250)]] | None = setting(
        None, label="settings.board.terrain_counts")
    """None = auto (see ``resolve``); explicit counts must sum to ``land_hexes`` (missing = 0)."""
    number_tokens: dict[Token, Annotated[int, Field(ge=0, le=250)]] | None = setting(
        None, label="settings.board.number_tokens")
    """token -> count. None = auto; explicit total must equal producing land hexes."""
    red_numbers: tuple[Token, ...] = setting((6, 8), label="settings.board.red_numbers", max_length=20)
    red_may_touch: bool = setting(False, label="settings.board.red_may_touch")
    red_rule_includes_fishing: bool = setting(True, label="settings.board.red_rule_includes_fishing")
    fishing_grounds: FishingGroundSettings = setting(label="settings.board.fishing_grounds",
                                                     factory=FishingGroundSettings)
    harbors: HarborSettings = setting(label="settings.board.harbors", factory=HarborSettings)
    robber_start: RobberStart = setting(RobberStart.DESERT, label="settings.board.robber_start")
    """``desert``: a random desert; on a board without deserts, a random land hex."""
    sea_margin: int = setting(2, label="settings.board.sea_margin", ge=1, le=6)
    """Rings of sea drawn around the island."""

    @model_validator(mode="after")
    def _counts_consistent(self) -> Self:
        if self.terrain_counts is not None:
            total = sum(self.terrain_counts.values())
            if total != self.land_hexes:
                raise _error("settings.board.terrain_sum",
                             "terrain_counts sum to {total}, land_hexes is {land_hexes}",
                             total=total, land_hexes=self.land_hexes)
        resolved = resolve_board_counts(self)
        producing = resolved.producing_land_hexes
        if producing < 1:
            raise _error("settings.board.no_producing_hexes", "the board has no producing land hex")
        if self.number_tokens is not None and len(resolved.number_tokens) != producing:
            raise _error("settings.board.token_count",
                         "number_tokens total {tokens} != producing land hexes {producing}",
                         tokens=len(resolved.number_tokens), producing=producing)
        if len(set(self.red_numbers)) != len(self.red_numbers):
            raise _error("settings.board.red_duplicates", "red_numbers has duplicates")
        token_values = set(self.number_tokens or STANDARD_NUMBER_TOKENS)
        unknown = sorted(set(self.red_numbers) - token_values)
        if unknown:
            raise _error("settings.board.red_not_token", "red_numbers {unknown} are not number token values",
                         unknown=unknown)
        return self


# ----------------------------------------------------------------------- clock
class ClockSettings(_Group):
    roll_interval_ms: int = setting(20000, label="settings.clock.roll_interval_ms", ge=5000, le=120000)
    dice_mode: DiceMode = setting(DiceMode.TWO_DICE, label="settings.clock.dice_mode")
    dice_count: int = setting(2, label="settings.clock.dice_count", stage=3, ge=1, le=4)
    dice_sides: int = setting(6, label="settings.clock.dice_sides", stage=3, ge=2, le=20)
    start_trigger: StartTrigger = setting(StartTrigger.FIRST_SETTLEMENT, label="settings.clock.start_trigger")
    pause_after_seven_ms: int = setting(0, label="settings.clock.pause_after_seven_ms", stage=3, ge=0, le=60000)
    allow_vote_pause: bool = setting(False, label="settings.clock.allow_vote_pause", stage=3)
    setup_pick_timer_ms: int | None = setting(None, label="settings.clock.setup_pick_timer_ms", stage=3,
                                              ge=1000, le=600000)

    @property
    def min_roll(self) -> int:
        return self.dice_count

    @property
    def max_roll(self) -> int:
        return self.dice_count * self.dice_sides

    @property
    def robber_roll(self) -> int:
        """The roll that triggers the robber: the most likely sum (7 with two six-sided dice)."""
        return self.dice_count * (self.dice_sides + 1) // 2


# --------------------------------------------------------------------- economy
class CostSettings(_Group):
    road: ResourceMap = setting({Resource.BRICK: 1, Resource.LUMBER: 1}, label="settings.economy.costs.road")
    settlement: ResourceMap = setting(
        {Resource.BRICK: 1, Resource.LUMBER: 1, Resource.WOOL: 1, Resource.GRAIN: 1},
        label="settings.economy.costs.settlement")
    city: ResourceMap = setting({Resource.GRAIN: 2, Resource.ORE: 3}, label="settings.economy.costs.city")
    dev_card: ResourceMap = setting({Resource.WOOL: 1, Resource.GRAIN: 1, Resource.ORE: 1},
                                    label="settings.economy.costs.dev_card", stage=2)
    settler: ResourceMap = setting(
        {Resource.GRAIN: 5, Resource.WOOL: 5, Resource.LUMBER: 3, Resource.FISH: 2},
        label="settings.economy.costs.settler", stage=3)


class ProductionSettings(_Group):
    settlement: int = setting(1, label="settings.economy.production_per.settlement", ge=0, le=10)
    city: int = setting(2, label="settings.economy.production_per.city", ge=0, le=10)


class StartingResourcesSettings(_Group):
    granting_settlements: int = setting(2, label="settings.economy.starting_resources.granting_settlements",
                                        ge=0, le=10)
    """How many of a player's first settlements grant starting resources."""
    cards_per_hex: int = setting(1, label="settings.economy.starting_resources.cards_per_hex", ge=0, le=10)
    include_fishing: bool = setting(True, label="settings.economy.starting_resources.include_fishing")


class BankSettings(_Group):
    per_resource: dict[Resource, Count] = setting({r: 19 for r in Resource},
                                                  label="settings.economy.bank.per_resource")
    """Cards per resource. Input may be a single int applied to every resource."""
    shortage_rule: ShortageRule = setting(ShortageRule.CLASSIC, label="settings.economy.bank.shortage_rule")

    @field_validator("per_resource", mode="before")
    @classmethod
    def _int_to_map(cls, value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool):
            return {r: value for r in Resource}
        return value

    @field_validator("per_resource")
    @classmethod
    def _all_resources(cls, value: dict[Resource, int]) -> dict[Resource, int]:
        missing = [r.value for r in Resource if r not in value]
        if missing:
            raise _error("settings.economy.bank_missing", "bank.per_resource lacks {missing}", missing=missing)
        return {r: value[r] for r in Resource}


class TradeRatioSettings(_Group):
    bank_ratio: int = setting(4, label="settings.economy.trade.bank_ratio", ge=1, le=10)


class EconomySettings(_Group):
    costs: CostSettings = setting(label="settings.economy.costs", factory=CostSettings)
    production_per: ProductionSettings = setting(label="settings.economy.production_per",
                                                 factory=ProductionSettings)
    starting_materials: ResourceMap = setting(
        {Resource.BRICK: 4, Resource.LUMBER: 4, Resource.WOOL: 2, Resource.GRAIN: 2},
        label="settings.economy.starting_materials")
    starting_materials_from_bank: bool = setting(True, label="settings.economy.starting_materials_from_bank")
    starting_resources: StartingResourcesSettings = setting(label="settings.economy.starting_resources",
                                                            factory=StartingResourcesSettings)
    bank: BankSettings = setting(label="settings.economy.bank", factory=BankSettings)
    trade: TradeRatioSettings = setting(label="settings.economy.trade", factory=TradeRatioSettings)


# ---------------------------------------------------------------------- pieces
class PieceSettings(_Group):
    roads: int = setting(15, label="settings.pieces.roads", ge=0, le=200)
    settlements: int = setting(5, label="settings.pieces.settlements", ge=1, le=100)
    cities: int = setting(4, label="settings.pieces.cities", ge=0, le=100)


# ----------------------------------------------------------------------- build
class BuildTimeSettings(_Group):
    road: int = setting(3000, label="settings.build.time_ms.road", ge=0, le=600000)
    settlement: int = setting(8000, label="settings.build.time_ms.settlement", ge=0, le=600000)
    city: int = setting(10000, label="settings.build.time_ms.city", ge=0, le=600000)


class BuildSettings(_Group):
    time_ms: BuildTimeSettings = setting(label="settings.build.time_ms", factory=BuildTimeSettings)
    network_builds_timed: bool = setting(True, label="settings.build.network_builds_timed")
    refund_pct: int = setting(100, label="settings.build.refund_pct", ge=0, le=100)
    conflict: ConflictRule = setting(ConflictRule.FIRST_TO_FINISH, label="settings.build.conflict")


# ----------------------------------------------------------------------- setup
class SetupSettings(_Group):
    mode: SetupMode = setting(SetupMode.SETTLERS, label="settings.setup.mode")
    settlements: int = setting(2, label="settings.setup.settlements", ge=1, le=10)
    roads: int = setting(2, label="settings.setup.roads", ge=0, le=10)
    road_touches_new_settlement: bool = setting(True, label="settings.setup.road_touches_new_settlement")
    network_build_during_setup: bool = setting(False, label="settings.setup.network_build_during_setup")
    """False: a player builds on the network only after finishing their own setup."""
    bank_trade_during_setup: bool = setting(True, label="settings.setup.bank_trade_during_setup")


# ---------------------------------------------------------------------- robber
class RobberSettings(_Group):
    enabled: bool = setting(True, label="settings.robber.enabled")
    card_limit: int = setting(7, label="settings.robber.card_limit", ge=0, le=100)
    steal_pct: int = setting(50, label="settings.robber.steal_pct", ge=0, le=100)
    steal_rounding: Rounding = setting(Rounding.FLOOR, label="settings.robber.steal_rounding")
    require_over_limit: bool = setting(True, label="settings.robber.require_over_limit")
    require_adjacent: bool = setting(False, label="settings.robber.require_adjacent")
    adjacency_timing: AdjacencyTiming = setting(AdjacencyTiming.BEFORE_MOVE, label="settings.robber.adjacency_timing")
    stolen_to_bank: bool = setting(True, label="settings.robber.stolen_to_bank", stage=3)
    move_on_seven: MoveOnSeven = setting(MoveOnSeven.RANDOM_NEIGHBOUR, label="settings.robber.move_on_seven")
    may_enter_fishing: bool = setting(False, label="settings.robber.may_enter_fishing", stage=3)
    may_enter_desert: bool = setting(True, label="settings.robber.may_enter_desert")
    knight_max_distance: int = setting(3, label="settings.robber.knight_max_distance", stage=2, ge=1, le=20)
    knight_steal: int = setting(1, label="settings.robber.knight_steal", stage=2, ge=0, le=20)
    friendly_min_points: int = setting(0, label="settings.robber.friendly_min_points", stage=3, ge=0, le=20)


# --------------------------------------------------------------------- settlers
class SettlerSettings(_Group):
    start_count: int = setting(1, label="settings.settlers.start_count", stage=3, ge=1, le=10)
    max: int = setting(4, label="settings.settlers.max", stage=3, ge=1, le=20)
    landing: Landing = setting(Landing.EVEN_COAST, label="settings.settlers.landing")
    ms_per_edge: int = setting(1500, label="settings.settlers.ms_per_edge", ge=100, le=60000)
    road_speed_pct: int = setting(200, label="settings.settlers.road_speed_pct", ge=100, le=1000)
    """Walking speed on the player's own roads, in percent of normal speed."""
    build_reach_edges: int = setting(0, label="settings.settlers.build_reach_edges", stage=3, ge=0, le=3)
    leave_after_setup: bool = setting(True, label="settings.settlers.leave_after_setup", stage=3)
    builder_required: BuilderRequired = setting(BuilderRequired.SETUP_ONLY, label="settings.settlers.builder_required")
    spawn_at: SpawnAt = setting(SpawnAt.OWN_BUILDING, label="settings.settlers.spawn_at")

    @model_validator(mode="after")
    def _start_le_max(self) -> Self:
        if self.start_count > self.max:
            raise _error("settings.settlers.start_gt_max", "settlers.start_count ({start}) > settlers.max ({max})",
                         start=self.start_count, max=self.max)
        return self


# ------------------------------------------------------------------- visibility
class SightSettings(_Group):
    road: int = setting(1, label="settings.visibility.sight.road", ge=0, le=10)
    settlement: int = setting(1, label="settings.visibility.sight.settlement", ge=0, le=10)
    city: int = setting(2, label="settings.visibility.sight.city", ge=0, le=10)
    settler: int = setting(1, label="settings.visibility.sight.settler", ge=0, le=10)


class VisibilitySettings(_Group):
    map: MapVisibility = setting(MapVisibility.OPEN, label="settings.visibility.map")
    sight: SightSettings = setting(label="settings.visibility.sight", stage=3, factory=SightSettings)
    hidden_numbers: bool = setting(False, label="settings.visibility.hidden_numbers", stage=3)
    hands: InfoVisibility = setting(InfoVisibility.COUNTS, label="settings.visibility.hands")
    dev_cards: InfoVisibility = setting(InfoVisibility.COUNTS, label="settings.visibility.dev_cards", stage=2)
    scores: ScoreVisibility = setting(ScoreVisibility.SHOWN, label="settings.visibility.scores")
    production_log: ProductionLog = setting(ProductionLog.ALL, label="settings.visibility.production_log")
    trade_offers: TradeOffers = setting(TradeOffers.PUBLIC, label="settings.visibility.trade_offers", stage=2)


# ---------------------------------------------------------------------- victory
class LongestRoadSettings(_Group):
    min: int = setting(5, label="settings.victory.longest_road.min", ge=1, le=50)
    """Minimum road length (segments) to claim the award."""
    points: int = setting(2, label="settings.victory.longest_road.points", ge=0, le=10)


class LargestArmySettings(_Group):
    min: int = setting(3, label="settings.victory.largest_army.min", ge=1, le=50)
    """Minimum knights played to claim the award."""
    points: int = setting(2, label="settings.victory.largest_army.points", ge=0, le=10)


class BuildingPointsSettings(_Group):
    settlement: int = setting(1, label="settings.victory.building_points.settlement", ge=0, le=10)
    city: int = setting(2, label="settings.victory.building_points.city", ge=0, le=10)
    """Total points of a city (it replaces the settlement's points)."""


class VictorySettings(_Group):
    target: int = setting(10, label="settings.victory.target", ge=5, le=20)
    building_points: BuildingPointsSettings = setting(label="settings.victory.building_points",
                                                      factory=BuildingPointsSettings)
    longest_road: LongestRoadSettings = setting(label="settings.victory.longest_road", stage=2,
                                                factory=LongestRoadSettings)
    largest_army: LargestArmySettings = setting(label="settings.victory.largest_army", stage=2,
                                                factory=LargestArmySettings)
    time_limit_ms: int | None = setting(None, label="settings.victory.time_limit_ms", stage=3,
                                        ge=60000, le=4 * _MAX_MS)


# ---------------------------------------------------------------------- trading
class TradingSettings(_Group):
    harbor_trade: bool = setting(True, label="settings.trading.harbor_trade")
    player_trades: bool = setting(True, label="settings.trading.player_trades", stage=2)
    offer_expiry_ms: int | None = setting(None, label="settings.trading.offer_expiry_ms", stage=2,
                                          ge=1000, le=600000)
    private_offers: bool = setting(False, label="settings.trading.private_offers", stage=3)


# -------------------------------------------------------------------- dev cards
class DevCardSettings(_Group):
    deck: dict[DevCardKind, Annotated[int, Field(ge=0, le=100)]] = setting(
        {DevCardKind.KNIGHT: 14, DevCardKind.VICTORY_POINT: 5, DevCardKind.ROAD_BUILDING: 2,
         DevCardKind.YEAR_OF_PLENTY: 2, DevCardKind.MONOPOLY: 2},
        label="settings.dev_cards.deck")
    cooldown: Cooldown = setting(Cooldown.PER_ROLL, label="settings.dev_cards.cooldown")
    cooldown_ms: int | None = setting(None, label="settings.dev_cards.cooldown_ms", ge=0, le=600000)
    vp_cards_must_be_played: bool = setting(True, label="settings.dev_cards.vp_cards_must_be_played")
    road_building_roads: int = setting(2, label="settings.dev_cards.road_building_roads", ge=0, le=10)
    year_of_plenty_cards: int = setting(2, label="settings.dev_cards.year_of_plenty_cards", ge=0, le=10)

    @model_validator(mode="after")
    def _cooldown_ms_given(self) -> Self:
        if self.cooldown is Cooldown.MS and self.cooldown_ms is None:
            raise _error("settings.dev_cards.cooldown_ms_missing", "cooldown 'ms' needs cooldown_ms")
        return self


# ------------------------------------------------------------------------- root
class GameSettings(_Group):
    """All per-game settings. Validate raw input with ``parse_settings`` (runs migrations)."""

    schema_version: int = setting(CURRENT_SCHEMA_VERSION, label="settings.schema_version",
                                  ge=CURRENT_SCHEMA_VERSION, le=CURRENT_SCHEMA_VERSION)
    preset: str = setting("classic", label="settings.preset", pattern=r"^[a-z0-9_]{1,32}$")
    players: PlayersSettings = setting(label="settings.players", factory=PlayersSettings)
    board: BoardSettings = setting(label="settings.board", factory=BoardSettings)
    clock: ClockSettings = setting(label="settings.clock", factory=ClockSettings)
    economy: EconomySettings = setting(label="settings.economy", factory=EconomySettings)
    pieces: PieceSettings = setting(label="settings.pieces", factory=PieceSettings)
    build: BuildSettings = setting(label="settings.build", factory=BuildSettings)
    setup: SetupSettings = setting(label="settings.setup", factory=SetupSettings)
    robber: RobberSettings = setting(label="settings.robber", factory=RobberSettings)
    settlers: SettlerSettings = setting(label="settings.settlers", factory=SettlerSettings)
    visibility: VisibilitySettings = setting(label="settings.visibility", factory=VisibilitySettings)
    victory: VictorySettings = setting(label="settings.victory", factory=VictorySettings)
    trading: TradingSettings = setting(label="settings.trading", factory=TradingSettings)
    dev_cards: DevCardSettings = setting(label="settings.dev_cards", stage=2, factory=DevCardSettings)

    @model_validator(mode="after")
    def _check_stage(self, info: ValidationInfo) -> Self:
        implemented = IMPLEMENTED_STAGE
        if info.context and "implemented_stage" in info.context:
            implemented = int(info.context["implemented_stage"])
        violations = stage_violations(self, implemented)
        if violations:
            fields = ", ".join(
                f"{v['field']}" + (f"={v['value']}" if "value" in v else "") + f" (stage {v['stage']})"
                for v in violations)
            raise _error("settings.later_stage",
                         "not available before a later stage (implemented: {implemented}): {fields}",
                         implemented=implemented, fields=fields, violations=violations)
        return self

    @model_validator(mode="after")
    def _check_cross_fields(self) -> Self:
        self._check_tokens_in_dice_range()
        self._check_pieces_cover_setup()
        self._check_bank_covers_starting_materials()
        return self

    def _check_tokens_in_dice_range(self) -> None:
        clock = self.clock
        resolved = resolve_board_counts(self)
        values = set(resolved.number_tokens) | set(resolved.fishing_tokens) | set(self.board.red_numbers)
        bad = sorted(v for v in values if not clock.min_roll <= v <= clock.max_roll or v == clock.robber_roll)
        if bad:
            raise _error("settings.board.token_out_of_range",
                         "token values {bad} are outside the dice range or equal the robber roll", bad=bad)

    def _check_pieces_cover_setup(self) -> None:
        if self.setup.settlements > self.pieces.settlements or self.setup.roads > self.pieces.roads:
            raise _error("settings.setup.exceeds_pieces", "setup needs more pieces than a player has")

    def _check_bank_covers_starting_materials(self) -> None:
        if not self.economy.starting_materials_from_bank:
            return
        bank = self.economy.bank.per_resource
        short = sorted(r.value for r, n in self.economy.starting_materials.items()
                       if n * self.players.max > bank[r])
        if short:
            raise _error("settings.economy.bank_too_small",
                         "bank cannot pay starting materials of {resources} to {players} players",
                         resources=short, players=self.players.max)


# ------------------------------------------------------------------ stage check
def _enum_values(value: Any) -> Iterator[Enum]:
    if isinstance(value, Enum):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _enum_values(k)
            yield from _enum_values(v)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _enum_values(item)


def _field_extra(model_cls: type[BaseModel], name: str) -> dict[str, Any]:
    extra = model_cls.model_fields[name].json_schema_extra
    return extra if isinstance(extra, dict) else {}


def _walk(model: BaseModel, default: BaseModel, path: str, parent_stage: int, implemented: int,
          out: list[dict[str, Any]]) -> None:
    cls = type(model)
    for name in cls.model_fields:
        extra = _field_extra(cls, name)
        stage = max(parent_stage, int(extra.get("stage", 1)))
        value, default_value = getattr(model, name), getattr(default, name)
        field_path = f"{path}.{name}" if path else name
        if isinstance(value, BaseModel):
            _walk(value, default_value, field_path, stage, implemented, out)
            continue
        if stage > implemented and value != default_value:
            out.append({"field": field_path, "stage": stage})
            continue
        for enum_value in _enum_values(value):
            if value_stage(enum_value) > implemented:
                out.append({"field": field_path, "value": enum_value.value, "stage": value_stage(enum_value)})
        above = extra.get("later_stage_above")
        if above and isinstance(value, int) and value > above["value"] and above["stage"] > implemented:
            out.append({"field": field_path, "value": value, "stage": above["stage"]})


def stage_violations(settings: GameSettings, implemented: int = IMPLEMENTED_STAGE) -> list[dict[str, Any]]:
    """Non-default later-stage fields and later-stage enum values, as ``{field, stage[, value]}``."""
    out: list[dict[str, Any]] = []
    _walk(settings, GameSettings.model_construct(), "", 1, implemented, out)
    return out
