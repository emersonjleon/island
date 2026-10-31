"""Timed construction (WP6): escrow, cancel/refund, first-to-finish, builder policy.

* ``build`` command: :func:`placement.check_build` (mode, placement, duplicate,
  piece, cost), then the builder policy; pay the cost into escrow
  (``Construction.paid``), reserve the piece and schedule ``construction_done`` at
  ``now + build.time_ms.<kind>``. Network builds complete at once when
  ``build.network_builds_timed`` is off (as do builds with a time of 0).
* ``cancel_build`` command: refund ``build.refund_pct`` of the escrow (floor per
  resource; the rest goes to the bank) and return the piece.
* ``SIG_SETTLER_DEPARTING``: cancel builds of that settler (``builder_left``).
* ``construction_done`` timer: re-check placement (cost is already paid). Illegal
  -> cancel (``conflict``). Else pay the escrow to the bank, place the piece (a
  city returns its settlement piece), ``emit(SIG_BUILT)``, and cancel every other
  construction that is no longer legal (``conflict``). Equal finish times resolve
  in timer order (earlier start first).

Event order on completion: ``Built``, then the ``SIG_BUILT`` listeners' events
(setup: ``StartingResources``/``Hand``, ``ClockStarted``, ``SetupComplete``,
``SettlerLeft``; victory: ``Points``), then ``ConstructionCancelled``/``Hand`` per
conflicting construction (ascending id). ``Built`` is *created* after the signal so
``points_after`` includes the new points.

Builder policy: a builder settler is required for setup builds
(``settlers.builder_required == "setup_only"``) or always (``"always"``). It must
be the player's settler, at rest (``movement.settler_at_rest``) on the target
vertex or an end of the target edge, and not already building. With no
``settler`` in the command, the lowest-id matching settler is used.

Reject codes (besides placement's): ``build.need_settler``,
``build.not_your_settler``, ``build.settler_busy``, ``build.unknown_construction``,
``build.not_your_construction``.

Invariant: bank + hands + escrow is constant per resource; per seat and kind,
``pieces_left`` + in-progress + placed is constant.
"""
from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Any

from engine.commands import Build, CancelBuild
from engine.errors import RuleError
from engine.events import Built, ConstructionCancelled, ConstructionStarted, Event, Hand
from engine.game import (
    SIG_BUILT, SIG_SETTLER_DEPARTING, TIMER_CONSTRUCTION_DONE, command_handler, connect, emit, timer_handler,
)
from engine.scheduler import Timer
from engine.settings.enums import BuilderRequired, BuildKind, Resource
from engine.state import Building, Construction, GameState

if TYPE_CHECKING:
    from engine.rules.placement import Mode

__all__ = [
    "handle_build", "handle_cancel_build", "construction_done", "on_settler_departing",
    "builder_required", "builder_spots", "choose_builder", "start_construction", "finish_construction",
    "cancel_construction", "cancel_builder_constructions", "cancel_conflicts", "build_time",
]


def _placement() -> ModuleType:
    from engine.rules import placement  # lazy: rule modules do not import each other at load time
    return placement


# ------------------------------------------------------------------ builder
def builder_required(state: GameState, setup: bool) -> bool:
    req = state.settings.settlers.builder_required
    return req is BuilderRequired.ALWAYS or (req is BuilderRequired.SETUP_ONLY and setup)


def builder_spots(state: GameState, kind: BuildKind, target: int) -> tuple[int, ...]:
    """Vertices a builder may stand on: the target vertex, or both ends of the edge."""
    if kind is BuildKind.ROAD:
        return tuple(state.board.board.edge_vertices[target])
    return (target,)


def _busy_settlers(state: GameState) -> set[int]:
    return {c.builder for c in state.constructions.values() if c.builder is not None}


def choose_builder(state: GameState, seat: int, kind: BuildKind, target: int, setup: bool,
                   settler: int | None) -> int | None:
    """The builder settler id (None if no builder is required). Raises ``RuleError``.
    ``target`` must already be a valid id for ``kind``."""
    if not builder_required(state, setup):
        return None
    from engine.rules import movement  # lazy: owned by WP5
    spots = builder_spots(state, kind, target)
    busy = _busy_settlers(state)
    params: dict[str, Any] = {"kind": kind.value, "target": target}
    if settler is not None:
        s = state.settlers.get(settler)
        if s is None or s.seat != seat:
            raise RuleError("build.not_your_settler", {**params, "settler": settler})
        if movement.settler_at_rest(state, settler) not in spots:
            raise RuleError("build.need_settler", {**params, "settler": settler})
        if settler in busy:
            raise RuleError("build.settler_busy", {**params, "settler": settler})
        return settler
    at_spot = [sid for sid in sorted(state.player(seat).settler_ids)
               if movement.settler_at_rest(state, sid) in spots]
    free = [sid for sid in at_spot if sid not in busy]
    if free:
        return free[0]
    if at_spot:
        raise RuleError("build.settler_busy", {**params, "settler": at_spot[0]})
    raise RuleError("build.need_settler", params)


# -------------------------------------------------------------------- start
def build_time(state: GameState, kind: BuildKind, setup: bool) -> int:
    if not setup and not state.settings.build.network_builds_timed:
        return 0
    return int(getattr(state.settings.build.time_ms, kind.value))


def _hand(state: GameState, seat: int, now_ms: int) -> Hand:
    return Hand(at=now_ms, seat=seat, hand=dict(state.player(seat).hand))


def start_construction(state: GameState, seat: int, kind: BuildKind, target: int, builder: int | None,
                       setup: bool, now_ms: int) -> list[Event]:
    """Pay into escrow, reserve the piece, schedule completion (or complete now).
    Assumes every check passed."""
    p = state.player(seat)
    cost = _placement().cost_of(state, kind)
    for r in Resource:
        p.hand[r] -= cost[r]
    p.pieces_left[kind] -= 1
    done = now_ms + build_time(state, kind, setup)
    c = Construction(id=state.next_id("construction"), seat=seat, kind=kind, target=target, builder=builder,
                     paid=cost, started_ms=now_ms, done_ms=done, setup=setup)
    state.constructions[c.id] = c
    events: list[Event] = [
        ConstructionStarted(at=now_ms, id=c.id, seat=seat, kind=kind, target=target, builder=builder,
                            t0=now_ms, t1=done, paid=dict(cost)),
        _hand(state, seat, now_ms),
    ]
    if done == now_ms:
        events += finish_construction(state, c, now_ms)
    else:
        c.timer_id = state.timers.schedule(done, TIMER_CONSTRUCTION_DONE, {"construction": c.id})
    return events


@command_handler("build")
def handle_build(state: GameState, seat: int, cmd: Build, now_ms: int) -> list[Event]:
    kind, target = cmd.kind, cmd.target
    placement = _placement()
    mode = placement.check_build(state, seat, kind, target)
    setup = mode == placement.SETUP
    builder = choose_builder(state, seat, kind, target, setup, cmd.settler)
    return start_construction(state, seat, kind, target, builder, setup, now_ms)


# ------------------------------------------------------------------- cancel
def cancel_construction(state: GameState, c: Construction, reason: str, now_ms: int) -> list[Event]:
    """Remove ``c``: refund ``refund_pct`` of the escrow (floor; rest to the bank),
    return the piece, cancel its timer."""
    state.timers.cancel(c.timer_id)
    c.timer_id = None
    state.constructions.pop(c.id, None)
    p = state.player(c.seat)
    pct = state.settings.build.refund_pct
    refund = {r: c.paid.get(r, 0) * pct // 100 for r in Resource}
    for r in Resource:
        p.hand[r] += refund[r]
        state.bank[r] += c.paid.get(r, 0) - refund[r]
    p.pieces_left[c.kind] = p.pieces_left.get(c.kind, 0) + 1
    events: list[Event] = [ConstructionCancelled(at=now_ms, id=c.id, seat=c.seat, reason=reason, refund=refund)]
    if any(refund.values()):
        events.append(_hand(state, c.seat, now_ms))
    return events


def cancel_builder_constructions(state: GameState, settler: int, reason: str, now_ms: int) -> list[Event]:
    """Cancel every in-progress construction built by ``settler`` (ascending id)."""
    events: list[Event] = []
    for cid in sorted(state.constructions):
        c = state.constructions.get(cid)
        if c is not None and c.builder == settler:
            events += cancel_construction(state, c, reason, now_ms)
    return events


@command_handler("cancel_build")
def handle_cancel_build(state: GameState, seat: int, cmd: CancelBuild, now_ms: int) -> list[Event]:
    c = state.constructions.get(cmd.construction)
    if c is None:
        raise RuleError("build.unknown_construction", {"construction": cmd.construction})
    if c.seat != seat:
        raise RuleError("build.not_your_construction", {"construction": cmd.construction})
    return cancel_construction(state, c, "cancelled", now_ms)


@connect(SIG_SETTLER_DEPARTING)
def on_settler_departing(state: GameState, now_ms: int, settler: int, **_: Any) -> list[Event]:
    return cancel_builder_constructions(state, settler, "builder_left", now_ms)


# ------------------------------------------------------------------- finish
def _mode(c: Construction) -> Mode:
    return "setup" if c.setup else "network"


def _still_legal(state: GameState, c: Construction) -> bool:
    return _placement().placement_error(state, c.seat, c.kind, c.target, _mode(c), recheck=True) is None


def _place(state: GameState, c: Construction) -> None:
    if c.kind is BuildKind.ROAD:
        state.roads[c.target] = c.seat
    elif c.kind is BuildKind.SETTLEMENT:
        state.buildings[c.target] = Building(seat=c.seat, kind=BuildKind.SETTLEMENT)
    else:
        # a city returns its settlement piece, a megacity its city piece
        replaced = BuildKind.SETTLEMENT if c.kind is BuildKind.CITY else BuildKind.CITY
        state.buildings[c.target] = Building(seat=c.seat, kind=c.kind)
        p = state.player(c.seat)
        p.pieces_left[replaced] = p.pieces_left.get(replaced, 0) + 1


def cancel_conflicts(state: GameState, now_ms: int) -> list[Event]:
    """Cancel (``conflict``) every in-progress construction whose placement is no
    longer legal, in ascending id order."""
    events: list[Event] = []
    for cid in sorted(state.constructions):
        c = state.constructions.get(cid)
        if c is not None and not _still_legal(state, c):
            events += cancel_construction(state, c, "conflict", now_ms)
    return events


def finish_construction(state: GameState, c: Construction, now_ms: int) -> list[Event]:
    """Complete ``c`` now (re-checking placement) and resolve conflicts."""
    if not _still_legal(state, c):
        return cancel_construction(state, c, "conflict", now_ms)
    state.timers.cancel(c.timer_id)
    c.timer_id = None
    state.constructions.pop(c.id, None)
    for r in Resource:
        state.bank[r] += c.paid.get(r, 0)
    _place(state, c)
    listener_events = emit(state, SIG_BUILT, now_ms, seat=c.seat, kind=c.kind, target=c.target,
                           setup=c.setup, construction=c.id)
    built = Built(at=now_ms, seat=c.seat, kind=c.kind, target=c.target, points_after=state.player(c.seat).points)
    return [built, *listener_events, *cancel_conflicts(state, now_ms)]


@timer_handler(TIMER_CONSTRUCTION_DONE)
def construction_done(state: GameState, timer: Timer, now_ms: int) -> list[Event]:
    c = state.constructions.get(timer.payload.get("construction", -1))
    if c is None or c.timer_id != timer.id:
        return []
    c.timer_id = None
    return finish_construction(state, c, now_ms)
