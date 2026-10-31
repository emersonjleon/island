"""Setup phase (WP6): starting materials, setup counters, starting resources,
setup completion (settlers leave) and the clock start.

* ``on_new_game`` (order 60): each player gets ``economy.starting_materials``
  (taken from the bank, as far as it holds them, when
  ``starting_materials_from_bank``); events ``StartingMaterials`` + ``Hand`` per seat.
* ``SIG_BUILT`` listener, in this order:
  1. setup build: decrement ``setup_remaining[kind]``; a setup settlement also sets
     ``last_setup_settlement`` and ``setup_settlements_built``;
  2. a setup settlement among the player's first
     ``starting_resources.granting_settlements``: ``cards_per_hex`` of each adjacent
     producing hex's resource (fishing grounds when ``include_fishing``; desert
     gives nothing; the robber does not block), each resource limited to what the
     bank holds -> ``StartingResources`` (+ ``Hand`` if anything was gained);
  3. any settlement while the clock is stopped (``clock.start_trigger ==
     "first_settlement"``): ``clock_started``, ``phase = "running"``, schedule the
     first ``dice_roll`` at ``now + roll_interval_ms`` -> ``ClockStarted``;
  4. setup build leaving nothing in ``setup_remaining``: ``setup_done`` ->
     ``SetupComplete``; with ``settlers.leave_after_setup`` the player's settlers
     are removed (their builds cancelled as ``builder_left``, their timers
     cancelled) -> ``SettlerLeft`` per settler.
"""
from __future__ import annotations

from typing import Any

from engine.events import ClockStarted, Event, Hand, SettlerLeft, SetupComplete, StartingMaterials, StartingResources
from engine.game import SIG_BUILT, TIMER_DICE_ROLL, connect, on_new_game
from engine.settings.enums import BuildKind, Resource, StartTrigger
from engine.state import GameState, empty_resources

__all__ = [
    "STARTING_MATERIALS_ORDER", "give_starting_materials", "on_built", "starting_resources_for",
    "grant_starting_resources", "start_clock", "complete_setup", "remove_settlers",
]

STARTING_MATERIALS_ORDER = 60


@on_new_game(order=STARTING_MATERIALS_ORDER)
def give_starting_materials(state: GameState, now_ms: int) -> list[Event]:
    eco = state.settings.economy
    events: list[Event] = []
    for p in state.players:
        got = empty_resources()
        for r in Resource:
            want = int(eco.starting_materials.get(r, 0))
            n = min(want, state.bank[r]) if eco.starting_materials_from_bank else want
            if eco.starting_materials_from_bank:
                state.bank[r] -= n
            p.hand[r] += n
            got[r] = n
        events.append(StartingMaterials(at=now_ms, seat=p.seat, materials=got))
        events.append(Hand(at=now_ms, seat=p.seat, hand=dict(p.hand)))
    return events


# ------------------------------------------------------------ starting resources
def starting_resources_for(state: GameState, vertex: int) -> dict[Resource, int]:
    """What a granting settlement on ``vertex`` is owed (before the bank limit)."""
    sr = state.settings.economy.starting_resources
    owed = empty_resources()
    for h in state.board.board.vertex_hexes[vertex]:
        r = state.board.hex_resource(h)
        if r is None or (h in state.board.fishing and not sr.include_fishing):
            continue
        owed[r] += sr.cards_per_hex
    return owed


def grant_starting_resources(state: GameState, seat: int, vertex: int, now_ms: int) -> list[Event]:
    p = state.player(seat)
    owed = starting_resources_for(state, vertex)
    gained = {r: min(owed[r], state.bank[r]) for r in Resource}
    for r in Resource:
        state.bank[r] -= gained[r]
        p.hand[r] += gained[r]
    events: list[Event] = [StartingResources(at=now_ms, seat=seat, gained=gained)]
    if any(gained.values()):
        events.append(Hand(at=now_ms, seat=seat, hand=dict(p.hand)))
    return events


# ------------------------------------------------------------------- clock
def start_clock(state: GameState, now_ms: int) -> list[Event]:
    """Start the dice clock once (no-op when already started)."""
    clock = state.settings.clock
    if state.clock_started or clock.start_trigger is not StartTrigger.FIRST_SETTLEMENT:
        return []
    state.clock_started = True
    if state.phase == "setup":
        state.phase = "running"
    due = now_ms + clock.roll_interval_ms
    state.roll_timer_id = state.timers.schedule(due, TIMER_DICE_ROLL, {})
    state.next_roll_at = due
    return [ClockStarted(at=now_ms, next_roll_at=due)]


# ------------------------------------------------------------- completion
def remove_settlers(state: GameState, seat: int, now_ms: int) -> list[Event]:
    """Take all of ``seat``'s settlers off the map (cancelling their builds and timers)."""
    from engine.rules import construction  # lazy: same package, avoids load-time coupling
    p = state.player(seat)
    events: list[Event] = []
    for sid in list(p.settler_ids):
        events += construction.cancel_builder_constructions(state, sid, "builder_left", now_ms)
        s = state.settlers.pop(sid, None)
        if s is not None:
            state.timers.cancel(s.timer_id)
            s.timer_id = None
        events.append(SettlerLeft(at=now_ms, settler=sid, seat=seat))
    p.settler_ids.clear()
    return events


def complete_setup(state: GameState, seat: int, now_ms: int) -> list[Event]:
    p = state.player(seat)
    p.setup_done = True
    events: list[Event] = [SetupComplete(at=now_ms, seat=seat)]
    if state.settings.settlers.leave_after_setup:
        events += remove_settlers(state, seat, now_ms)
    return events


@connect(SIG_BUILT)
def on_built(state: GameState, now_ms: int, seat: int, kind: BuildKind, target: int, setup: bool,
             **_: Any) -> list[Event]:
    p = state.player(seat)
    events: list[Event] = []
    if setup:
        p.setup_remaining[kind] = max(0, p.setup_remaining.get(kind, 0) - 1)
        if kind is BuildKind.SETTLEMENT:
            p.setup_settlements_built += 1
            p.last_setup_settlement = target
            if p.setup_settlements_built <= state.settings.economy.starting_resources.granting_settlements:
                events += grant_starting_resources(state, seat, target, now_ms)
    if kind is BuildKind.SETTLEMENT:
        events += start_clock(state, now_ms)
    if setup and not p.setup_done and all(v <= 0 for v in p.setup_remaining.values()):
        events += complete_setup(state, seat, now_ms)
    return events
