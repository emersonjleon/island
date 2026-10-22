"""Game state: plain mutable dataclasses.

Everything that influences the game lives here, so ``codec.dump`` captures a
game completely (RNG and timers included). Ids:

* vertices, edges and hexes are the dense ids of ``state.board.board``
  (:class:`engine.board.topology.Board`);
* settlers and constructions get ids from :meth:`GameState.next_id`
  (kinds ``"settler"`` and ``"construction"``), starting at 1;
* timers get ids from ``state.timers`` (:class:`engine.scheduler.Scheduler`).

Resource maps (hands, bank, escrow) always contain all six :class:`Resource`
keys. ``ext`` is the extension slot for later stages (dev cards, offers,
visibility); its content must be JSON-safe with string keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from engine.board.model import GeneratedBoard
from engine.errors import EngineError
from engine.rng import Rng
from engine.scheduler import Scheduler
from engine.settings.enums import BuildKind, Resource
from engine.settings.models import GameSettings

__all__ = [
    "Phase", "PHASES", "SeatInfo", "PlayerState", "SettlerStep", "Settler", "Construction", "Building",
    "GameState", "empty_resources",
]

Phase = Literal["setup", "running", "finished"]
PHASES: tuple[str, ...] = ("setup", "running", "finished")


def empty_resources() -> dict[Resource, int]:
    """A resource map with every resource at 0 (enum order)."""
    return {r: 0 for r in Resource}


@dataclass
class SeatInfo:
    seat: int
    user_id: int | None
    name: str
    colour: str


@dataclass
class PlayerState:
    seat: int
    info: SeatInfo
    hand: dict[Resource, int] = field(default_factory=empty_resources)
    pieces_left: dict[BuildKind, int] = field(default_factory=dict)          # road / settlement / city
    setup_remaining: dict[BuildKind, int] = field(default_factory=dict)      # settlement / road
    setup_done: bool = False
    last_setup_settlement: int | None = None    # vertex id of the newest setup settlement
    setup_settlements_built: int = 0
    points: int = 0                             # cached; victory keeps it up to date
    settler_ids: list[int] = field(default_factory=list)

    @property
    def hand_count(self) -> int:
        return sum(self.hand.values())


@dataclass
class SettlerStep:
    """The edge a settler is currently walking: from ``from_v`` at ``t0`` to ``to_v`` at ``t1``."""
    edge: int
    from_v: int
    to_v: int
    t0: int
    t1: int


@dataclass
class Settler:
    id: int
    seat: int
    vertex: int                          # current vertex, or the vertex it last left while stepping
    path: list[int] = field(default_factory=list)   # queued vertices still to walk to (after step.to_v)
    step: SettlerStep | None = None
    timer_id: int | None = None          # pending "settler_arrive" timer


@dataclass
class Construction:
    id: int
    seat: int
    kind: BuildKind
    target: int                          # vertex id (settlement/city) or edge id (road)
    builder: int | None                  # settler id, or None for network builds
    paid: dict[Resource, int]            # escrow, returned (by refund_pct) on cancel
    started_ms: int
    done_ms: int
    setup: bool = False                  # counts towards the player's setup
    timer_id: int | None = None          # pending "construction_done" timer


@dataclass
class Building:
    seat: int
    kind: BuildKind                      # settlement or city


@dataclass
class GameState:
    settings: GameSettings
    board: GeneratedBoard
    rng: Rng
    seed: int
    players: list[PlayerState]
    bank: dict[Resource, int]
    now_ms: int = 0
    phase: Phase = "setup"
    buildings: dict[int, Building] = field(default_factory=dict)      # vertex id -> building
    roads: dict[int, int] = field(default_factory=dict)               # edge id -> seat
    settlers: dict[int, Settler] = field(default_factory=dict)        # settler id -> settler
    constructions: dict[int, Construction] = field(default_factory=dict)
    robber_hex: int | None = None
    clock_started: bool = False
    next_roll_at: int | None = None
    roll_timer_id: int | None = None
    last_roll: list[int] | None = None   # dice faces of the latest roll
    dice_history: list[int] = field(default_factory=list)             # sums, oldest first
    timers: Scheduler = field(default_factory=Scheduler)
    id_counters: dict[str, int] = field(default_factory=dict)         # kind -> next id
    winner: int | None = None
    finished_at: int | None = None
    buildable_cache: dict[int, dict[str, Any]] = field(default_factory=dict)  # seat -> last sent sets
    ext: dict[str, Any] = field(default_factory=dict)

    def next_id(self, kind: str) -> int:
        """Next id for an entity kind (``"settler"``, ``"construction"``, ...), from 1."""
        n = self.id_counters.get(kind, 1)
        self.id_counters[kind] = n + 1
        return n

    def player(self, seat: int) -> PlayerState:
        if not isinstance(seat, int) or isinstance(seat, bool) or not 0 <= seat < len(self.players):
            raise EngineError(f"unknown seat {seat!r}")
        return self.players[seat]

    def has_seat(self, seat: Any) -> bool:
        return isinstance(seat, int) and not isinstance(seat, bool) and 0 <= seat < len(self.players)

    @property
    def finished(self) -> bool:
        return self.phase == "finished"
