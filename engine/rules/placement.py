"""Placement legality (WP6): distance rule, connectivity, pieces, costs, buildable sets.

Everything here is a **pure query** on the state (no mutation), except the
``after_step`` hook that maintains ``state.buildable_cache``. Construction uses
these checks before starting a build and again when it finishes; bots (WP8) can
use :func:`legal_targets` / :func:`build_error` to pick legal moves.

Build modes (per player and kind, see :func:`build_mode`):

* ``"setup"`` -- the player has not finished their own setup and still has a free
  setup slot for this kind (``setup_remaining[kind]`` minus in-progress setup
  builds). Settlement: land, empty, distance rule. Road: land, empty, touches the
  player's newest finished setup settlement (``setup.road_touches_new_settlement``;
  otherwise any own building).
* ``"network"`` -- after the player's own setup (or during it when
  ``setup.network_build_during_setup``). Settlement: land, empty, distance rule,
  touches an own finished road. Road: land, empty, touches an own building, or an
  own road at an end vertex that holds no opponent building. City: replaces an own
  finished settlement.

In-progress constructions of *other* players never block a target (first to
finish wins); the same player cannot build the same kind on the same target twice.

Reject codes (``RuleError.code``; params always include ``kind`` and ``target``):
``build.not_land``, ``build.occupied``, ``build.distance_rule``,
``build.not_connected``, ``build.road_needs_settlement``,
``build.not_own_settlement``, ``build.setup_unfinished``, ``build.setup_limit``,
``build.already_building``, ``build.no_piece``, ``build.cannot_afford``
(``missing``: resource -> count).
"""
from __future__ import annotations

from typing import Literal

from engine.errors import RuleError
from engine.events import Buildable, Event
from engine.game import after_step
from engine.settings.enums import BuildKind, Resource
from engine.state import GameState, PlayerState
from engine.views import register_buildable_provider

__all__ = [
    "Mode", "SETUP", "NETWORK", "BUILDABLE_ORDER",
    "cost_of", "missing_resources", "can_afford", "pending_setup", "build_mode", "mode_error",
    "road_connected", "settlement_error", "road_error", "city_error", "placement_error",
    "build_error", "check_build", "legal_targets", "buildable", "buildable_view", "update_buildable",
]

Mode = Literal["setup", "network"]
SETUP: Mode = "setup"
NETWORK: Mode = "network"
BUILDABLE_ORDER = 200

_KEYS = {BuildKind.ROAD: "roads", BuildKind.SETTLEMENT: "settlements", BuildKind.CITY: "cities"}


def _err(code: str, kind: BuildKind, target: int | None, **extra: object) -> RuleError:
    return RuleError(code, {"kind": kind.value, "target": target, **extra})


# ------------------------------------------------------------------ economy
def cost_of(state: GameState, kind: BuildKind) -> dict[Resource, int]:
    """Full resource map of the cost of ``kind`` (``settings.economy.costs``)."""
    cost = getattr(state.settings.economy.costs, kind.value)
    return {r: int(cost.get(r, 0)) for r in Resource}


def missing_resources(hand: dict[Resource, int], cost: dict[Resource, int]) -> dict[str, int]:
    """Resource value -> how many are lacking (empty when affordable)."""
    return {r.value: cost[r] - hand.get(r, 0) for r in Resource if cost.get(r, 0) > hand.get(r, 0)}


def can_afford(player: PlayerState, cost: dict[Resource, int]) -> bool:
    return not missing_resources(player.hand, cost)


# --------------------------------------------------------------------- mode
def pending_setup(state: GameState, seat: int, kind: BuildKind) -> int:
    """In-progress setup constructions of ``seat`` of ``kind``."""
    return sum(1 for c in state.constructions.values() if c.seat == seat and c.kind is kind and c.setup)


def mode_error(state: GameState, seat: int, kind: BuildKind) -> tuple[Mode | None, RuleError | None]:
    """``(mode, None)`` if ``seat`` may build ``kind`` now, else ``(None, error)``."""
    p = state.player(seat)
    if p.setup_done:
        return NETWORK, None
    during = state.settings.setup.network_build_during_setup
    remaining = p.setup_remaining.get(kind, 0) if kind is not BuildKind.CITY else 0
    if remaining > 0:
        if remaining - pending_setup(state, seat, kind) > 0:
            return SETUP, None
        if not during:
            return None, _err("build.setup_limit", kind, None, remaining=remaining)
    if during:
        return NETWORK, None
    return None, _err("build.setup_unfinished", kind, None)


def build_mode(state: GameState, seat: int, kind: BuildKind) -> Mode:
    """The mode a new ``kind`` build of ``seat`` would have. Raises ``RuleError``."""
    mode, err = mode_error(state, seat, kind)
    if err is not None:
        raise err
    assert mode is not None
    return mode


# ---------------------------------------------------------------- placement
def _land_vertex(state: GameState, v: int) -> bool:
    b = state.board.board
    return 0 <= v < len(b.vertices) and b.land_vertex(v)


def _land_edge(state: GameState, e: int) -> bool:
    b = state.board.board
    return 0 <= e < len(b.edges) and b.land_edge(e)


def _own_building_at(state: GameState, seat: int, v: int) -> bool:
    b = state.buildings.get(v)
    return b is not None and b.seat == seat


def road_connected(state: GameState, seat: int, edge: int) -> bool:
    """Edge touches an own building, or an own road at an end vertex not holding
    an opponent's building (a road cannot continue *through* an opponent)."""
    board = state.board.board
    for x in board.edge_vertices[edge]:
        b = state.buildings.get(x)
        if b is not None:
            if b.seat == seat:
                return True
            continue
        if any(e != edge and state.roads.get(e) == seat for e in board.vertex_edges[x]):
            return True
    return False


def settlement_error(state: GameState, seat: int, vertex: int, mode: Mode) -> RuleError | None:
    k = BuildKind.SETTLEMENT
    if not _land_vertex(state, vertex):
        return _err("build.not_land", k, vertex)
    if vertex in state.buildings:
        return _err("build.occupied", k, vertex)
    board = state.board.board
    if any(n in state.buildings for n in board.vertex_neighbors[vertex]):
        return _err("build.distance_rule", k, vertex)
    if mode == NETWORK and not any(state.roads.get(e) == seat for e in board.vertex_edges[vertex]):
        return _err("build.not_connected", k, vertex)
    return None


def road_error(state: GameState, seat: int, edge: int, mode: Mode, recheck: bool = False) -> RuleError | None:
    """``recheck`` (at completion): a setup road only needs to touch any own building,
    since the player's newest setup settlement may have changed meanwhile."""
    k = BuildKind.ROAD
    if not _land_edge(state, edge):
        return _err("build.not_land", k, edge)
    if edge in state.roads:
        return _err("build.occupied", k, edge)
    ends = state.board.board.edge_vertices[edge]
    if mode == SETUP:
        last = state.player(seat).last_setup_settlement
        if state.settings.setup.road_touches_new_settlement and not recheck:
            ok = last is not None and last in ends and _own_building_at(state, seat, last)
        else:
            ok = any(_own_building_at(state, seat, x) for x in ends)
        return None if ok else _err("build.road_needs_settlement", k, edge)
    if not road_connected(state, seat, edge):
        return _err("build.not_connected", k, edge)
    return None


def city_error(state: GameState, seat: int, vertex: int) -> RuleError | None:
    k = BuildKind.CITY
    if not _land_vertex(state, vertex):
        return _err("build.not_land", k, vertex)
    b = state.buildings.get(vertex)
    if b is None or b.seat != seat or b.kind is not BuildKind.SETTLEMENT:
        return _err("build.not_own_settlement", k, vertex)
    return None


def placement_error(state: GameState, seat: int, kind: BuildKind, target: int, mode: Mode,
                    recheck: bool = False) -> RuleError | None:
    """Board-position rules only (no mode, piece, cost, duplicate or builder checks)."""
    if kind is BuildKind.SETTLEMENT:
        return settlement_error(state, seat, target, mode)
    if kind is BuildKind.ROAD:
        return road_error(state, seat, target, mode, recheck)
    return city_error(state, seat, target)


# ------------------------------------------------------------- full checks
def _resource_error(state: GameState, seat: int, kind: BuildKind, target: int | None) -> RuleError | None:
    p = state.player(seat)
    if p.pieces_left.get(kind, 0) <= 0:
        return _err("build.no_piece", kind, target)
    missing = missing_resources(p.hand, cost_of(state, kind))
    if missing:
        return _err("build.cannot_afford", kind, target, missing=missing)
    return None


def _own_duplicate(state: GameState, seat: int, kind: BuildKind, target: int) -> bool:
    return any(c.seat == seat and c.kind is kind and c.target == target for c in state.constructions.values())


def build_error(state: GameState, seat: int, kind: BuildKind, target: int) -> RuleError | None:
    """Every rule for starting a build except the builder settler. Check order:
    mode, placement, duplicate, piece, cost."""
    mode, err = mode_error(state, seat, kind)
    if err is not None:
        return _err(err.code, kind, target, **{k: v for k, v in err.params.items() if k not in ("kind", "target")})
    assert mode is not None
    err = placement_error(state, seat, kind, target, mode)
    if err is not None:
        return err
    if _own_duplicate(state, seat, kind, target):
        return _err("build.already_building", kind, target)
    return _resource_error(state, seat, kind, target)


def check_build(state: GameState, seat: int, kind: BuildKind, target: int) -> Mode:
    """Raise the first :func:`build_error`; return the build mode when legal."""
    err = build_error(state, seat, kind, target)
    if err is not None:
        raise err
    return build_mode(state, seat, kind)


def legal_targets(state: GameState, seat: int, kind: BuildKind) -> list[int]:
    """Sorted ids where ``seat`` may start a ``kind`` build now (ignoring the
    builder settler). Same result as filtering every id with :func:`build_error`."""
    if state.phase == "finished":
        return []
    mode, err = mode_error(state, seat, kind)
    if err is not None or _resource_error(state, seat, kind, None) is not None:
        return []
    assert mode is not None
    board = state.board.board
    if kind is BuildKind.ROAD:
        candidates: list[int] = list(board.land_edges)
    elif kind is BuildKind.SETTLEMENT:
        candidates = list(board.land_vertices)
    else:
        candidates = sorted(v for v, b in state.buildings.items() if b.seat == seat)
    return [t for t in candidates
            if placement_error(state, seat, kind, t, mode) is None and not _own_duplicate(state, seat, kind, t)]


def buildable(state: GameState, seat: int) -> dict[str, list[int]]:
    """``{"roads", "settlements", "cities"}``: what ``seat`` can legally start and
    afford now. During setup the builder position is ignored (the client guides
    the settler)."""
    return {key: legal_targets(state, seat, kind) for kind, key in _KEYS.items()}


def buildable_view(state: GameState, seat: int) -> dict[str, list[int]]:
    """Provider for ``views.project_state``: the set last sent to ``seat`` (kept
    current by :func:`update_buildable` after every step), computed if absent."""
    cached = state.buildable_cache.get(seat)
    if cached is not None:
        return {k: list(v) for k, v in cached.items()}
    return buildable(state, seat)


register_buildable_provider(buildable_view)


@after_step(order=BUILDABLE_ORDER)
def update_buildable(state: GameState, now_ms: int) -> list[Event]:
    """Emit a private ``Buildable`` per seat whose set changed since the last one sent."""
    events: list[Event] = []
    for p in state.players:
        cur = buildable(state, p.seat)
        if state.buildable_cache.get(p.seat) != cur:
            state.buildable_cache[p.seat] = cur
            events.append(Buildable(at=now_ms, seat=p.seat, **cur))
    return events
