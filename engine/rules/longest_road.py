"""Longest Road (stage 2): road lengths, the award and its points.

* :func:`road_length` -- the longest trail of a seat's finished roads: each road
  segment counts once, and a vertex with another player's building splits the
  road there (the trail may end at that vertex but not pass through it).
* ``@connect(SIG_BUILT)`` (:func:`on_built`): after a road (it can lengthen the
  builder's road) or a settlement (it can split an opponent's road), recompute
  every seat's length and the holder; cities and megacities change nothing.
  Emits ``LongestRoad`` when a length or the holder changed, and ``Points`` for
  each seat whose score changed. A player who reaches the target this way wins
  at once (:func:`engine.rules.victory.finish`).

Award rules (``settings.victory.longest_road``):

* a seat needs at least ``min`` segments to hold it;
* the holder keeps it while tied for the longest; another seat takes it only
  with a strictly longer road;
* when the holder's road is split and several other seats tie for the longest,
  nobody holds it until one of them is strictly longest;
* the holder gets ``points`` extra points.

State: ``state.ext["longest_road"] = {"holder": seat | None, "lengths": {"<seat>": n}}``.
"""
from __future__ import annotations

from typing import Any

from engine.events import Event, LongestRoad, Points
from engine.game import SIG_BUILT, connect
from engine.rules import victory
from engine.settings.enums import BuildKind
from engine.state import GameState

__all__ = ["BUILT_ORDER", "EXT_KEY", "road_length", "lengths", "holder", "next_holder", "on_built"]

BUILT_ORDER = victory.BUILT_ORDER + 10   # after the building points of the same build
EXT_KEY = "longest_road"


def road_length(state: GameState, seat: int) -> int:
    """Segments in ``seat``'s longest trail of finished roads."""
    board = state.board.board
    own = {e for e, s in state.roads.items() if s == seat}
    if not own:
        return 0

    def blocked(v: int) -> bool:
        b = state.buildings.get(v)
        return b is not None and b.seat != seat

    def walk(v: int, used: set[int]) -> int:
        best = 0
        for e, n in zip(board.vertex_edges[v], board.vertex_neighbors[v]):
            if e in own and e not in used:
                used.add(e)
                best = max(best, 1 + (0 if blocked(n) else walk(n, used)))
                used.discard(e)
        return best

    starts = {v for e in own for v in board.edge_vertices[e]}
    return max(walk(v, set()) for v in starts)


def _ext(state: GameState) -> dict[str, Any]:
    return state.ext.setdefault(EXT_KEY, {"holder": None, "lengths": {}})


def lengths(state: GameState) -> dict[int, int]:
    """Last computed length per seat (read-only: does not create the ext entry)."""
    return {int(k): v for k, v in state.ext.get(EXT_KEY, {}).get("lengths", {}).items()}


def holder(state: GameState) -> int | None:
    return state.ext.get(EXT_KEY, {}).get("holder")


def next_holder(current: int | None, by_seat: dict[int, int], minimum: int) -> int | None:
    """Who holds the award given the new lengths (see the module rules)."""
    best = max(by_seat.values(), default=0)
    if best < minimum:
        return None
    leaders = [s for s, n in by_seat.items() if n == best]
    if current in leaders:
        return current
    return leaders[0] if len(leaders) == 1 else None


@connect(SIG_BUILT, order=BUILT_ORDER)
def on_built(state: GameState, now_ms: int, *, seat: int, kind: BuildKind, target: int, setup: bool,
             construction: int, **_: Any) -> list[Event]:
    if BuildKind(kind) not in (BuildKind.ROAD, BuildKind.SETTLEMENT) or state.phase == "finished":
        return []
    ext = _ext(state)
    cfg = state.settings.victory.longest_road
    new_lengths = {p.seat: road_length(state, p.seat) for p in state.players}
    old_holder = ext["holder"]
    new_holder = next_holder(old_holder, new_lengths, cfg.min)
    if new_lengths == lengths(state) and new_holder == old_holder:
        return []
    ext["lengths"] = {str(s): n for s, n in new_lengths.items()}
    ext["holder"] = new_holder
    events: list[Event] = [LongestRoad(at=now_ms, seat=new_holder, previous=old_holder,
                                       lengths=new_lengths)]
    if new_holder == old_holder or cfg.points == 0:
        return events
    if old_holder is not None:
        p = state.player(old_holder)
        p.points -= cfg.points
        events.append(Points(at=now_ms, seat=old_holder, points=p.points))
    if new_holder is not None:
        p = state.player(new_holder)
        p.points += cfg.points
        events.append(Points(at=now_ms, seat=new_holder, points=p.points))
        if p.points >= state.settings.victory.target:
            victory.finish(state, new_holder, now_ms)
    return events
