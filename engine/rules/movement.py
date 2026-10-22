"""Settler movement (WP5): landing, paths, per-edge stepping, interrupts.

* ``@on_new_game(order=50)`` :func:`land_settlers`: ``settlers.start_count`` settlers
  per player at evenly spread coastal landing points; emits ``SettlerLanded``.
* ``@command_handler("move_settler")`` :func:`move_settler`: validate, then set the
  queued path. ``replace`` drops the queue (a settler mid-edge finishes that edge and
  continues from its end vertex); ``append`` paths from the end of the queue.
* ``@timer_handler(TIMER_SETTLER_ARRIVE)`` :func:`settler_arrive`: arrive at
  ``step.to_v``, emit ``SettlerArrived``, start the next edge if the path continues.

Leaving a vertex (:func:`_start_step`) always runs, in this order:
``emit(SIG_SETTLER_DEPARTING, settler=id, vertex=v)`` (listener events first), then
``settler.step`` + ``settler_arrive`` timer, then ``SettlerStepEvent``. The edge time
is computed when the settler enters the edge (own finished road -> faster).

Reject codes of ``move_settler`` (params in brackets):

* ``movement.unknown_settler`` {settler}
* ``movement.not_your_settler`` {settler}
* ``movement.unknown_vertex`` {vertex} -- id outside the board
* ``movement.not_land`` {vertex} -- vertex touches no land hex
* ``movement.unreachable`` {settler, from, to}
"""
from __future__ import annotations

from engine.board import walkgraph
from engine.errors import EngineError, RuleError
from engine.events import Event, SettlerArrived, SettlerLanded, SettlerPath, SettlerStepEvent
from engine.game import (
    SIG_SETTLER_DEPARTING, TIMER_SETTLER_ARRIVE, command_handler, emit, on_new_game, timer_handler,
)
from engine.commands import MoveSettler
from engine.scheduler import Timer
from engine.settings.enums import Landing
from engine.state import GameState, Settler, SettlerStep

__all__ = ["land_settlers", "move_settler", "settler_arrive", "settler_at_rest", "LANDING_ORDER"]

LANDING_ORDER = 50


# ---------------------------------------------------------------------- query
def settler_at_rest(state: GameState, settler_id: int) -> int | None:
    """The settler's vertex if it exists, is not walking an edge and has no queued
    path; otherwise None."""
    s = state.settlers.get(settler_id)
    if s is None or s.step is not None or s.path:
        return None
    return s.vertex


# -------------------------------------------------------------------- landing
@on_new_game(order=LANDING_ORDER)
def land_settlers(state: GameState, now_ms: int) -> list[Event]:
    """Create the starting settlers. Point ``k`` (of ``players * start_count``) goes to
    seat ``k % players``, so each player's settlers are spread around the coast too."""
    ss = state.settings.settlers
    if ss.landing is not Landing.EVEN_COAST:
        raise EngineError(f"movement: unsupported landing {ss.landing!r}")
    n = len(state.players)
    points = walkgraph.landing_points(state.board.board, n * ss.start_count, state.rng)
    events: list[Event] = []
    for k, v in enumerate(points):
        seat = k % n
        sid = state.next_id("settler")
        state.settlers[sid] = Settler(id=sid, seat=seat, vertex=v)
        state.players[seat].settler_ids.append(sid)
        events.append(SettlerLanded(at=now_ms, settler=sid, seat=seat, vertex=v))
    return events


# -------------------------------------------------------------------- command
def _queue_end(s: Settler, replace: bool) -> int:
    """Vertex a new path starts from."""
    if not replace and s.path:
        return s.path[-1]
    return s.step.to_v if s.step is not None else s.vertex


@command_handler("move_settler")
def move_settler(state: GameState, seat: int, cmd: MoveSettler, now_ms: int) -> list[Event]:
    s = state.settlers.get(cmd.settler)
    if s is None:
        raise RuleError("movement.unknown_settler", {"settler": cmd.settler})
    if s.seat != seat:
        raise RuleError("movement.not_your_settler", {"settler": cmd.settler})
    board = state.board.board
    if cmd.to_vertex >= len(board.vertices):
        raise RuleError("movement.unknown_vertex", {"vertex": cmd.to_vertex})
    if not board.land_vertex(cmd.to_vertex):
        raise RuleError("movement.not_land", {"vertex": cmd.to_vertex})
    replace = cmd.mode == "replace"
    start = _queue_end(s, replace)
    path = walkgraph.shortest_path(state, seat, start, cmd.to_vertex)
    if path is None:
        raise RuleError("movement.unreachable", {"settler": s.id, "from": start, "to": cmd.to_vertex})
    # ---- validated; mutate from here on
    s.path = path if replace else s.path + path
    events: list[Event] = []
    if s.step is None and s.path:
        events.extend(_start_step(state, s, now_ms))
    events.append(SettlerPath(at=now_ms, settler=s.id, path=list(s.path)))
    return events


# -------------------------------------------------------------------- walking
def _start_step(state: GameState, s: Settler, now_ms: int) -> list[Event]:
    """Leave ``s.vertex`` towards ``s.path[0]`` (``s.step`` must be None)."""
    from_v = s.vertex
    events = emit(state, SIG_SETTLER_DEPARTING, now_ms, settler=s.id, vertex=from_v)
    if state.settlers.get(s.id) is not s or s.step is not None or not s.path:
        return events                       # a listener removed or moved the settler
    to_v = s.path.pop(0)
    edge = walkgraph.edge_between(state.board.board, from_v, to_v)
    if edge is None:                        # cannot happen for paths from shortest_path
        s.path = []
        return events
    t1 = now_ms + walkgraph.edge_cost_ms(state, s.seat, edge)
    s.step = SettlerStep(edge=edge, from_v=from_v, to_v=to_v, t0=now_ms, t1=t1)
    s.timer_id = state.timers.schedule(t1, TIMER_SETTLER_ARRIVE, {"settler": s.id})
    events.append(SettlerStepEvent(at=now_ms, settler=s.id, edge=edge, from_v=from_v, to_v=to_v,
                                   t0=now_ms, t1=t1))
    return events


@timer_handler(TIMER_SETTLER_ARRIVE)
def settler_arrive(state: GameState, timer: Timer, now_ms: int) -> list[Event]:
    """Finish the current edge. Stale timers (settler gone, or not its pending timer)
    are ignored."""
    s = state.settlers.get(timer.payload.get("settler"))  # type: ignore[arg-type]
    if s is None or s.step is None or s.timer_id != timer.id:
        return []
    s.vertex = s.step.to_v
    s.step = None
    s.timer_id = None
    events: list[Event] = [SettlerArrived(at=now_ms, settler=s.id, vertex=s.vertex)]
    if s.path:
        events.extend(_start_step(state, s, now_ms))
    return events
