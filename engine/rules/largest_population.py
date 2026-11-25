"""Largest Population: an award, like the Longest Road, for the player with the most settlers.

Played only when settlers stay on the island after setup (``settlers.leave_after_setup``
off), with or without ages (Emerson, Nov 25, 2026: the points go to whoever has the most
settlers). A seat's population is the number of settlers it has now.

* ``@after_step(order=ORDER)`` (:func:`update_population`): after every step, recompute
  every population and the holder. Emits ``LargestPopulation`` when a population or the
  holder changed, and ``Points`` for each seat whose score changed. A player who reaches
  the target this way wins at once (:mod:`engine.rules.victory` runs after this hook).

Award rules (the same as the Longest Road, :func:`engine.rules.longest_road.next_holder`):
a seat needs at least ``settlers.largest_population.min`` settlers; the holder keeps it
while tied; another seat takes it only with strictly more; the holder gets ``points``
extra points. Resigned players hold nothing.

State: ``state.ext["largest_population"] = {"holder": seat | None, "population": {"<seat>": n}}``.
"""
from __future__ import annotations

from typing import Any

from engine.events import Event, LargestPopulation
from engine.game import after_step
from engine.rules import longest_road, victory
from engine.state import GameState
from engine.views import register_state_extension

__all__ = ["ORDER", "EXT_KEY", "active", "population", "populations", "holder", "update_population", "state_view"]

ORDER = 800            # before victory (900)
EXT_KEY = "largest_population"


def active(state: GameState) -> bool:
    """Whether the award is played: settlers stay after setup."""
    return not state.settings.settlers.leave_after_setup


def population(state: GameState, seat: int) -> int:
    """How many settlers ``seat`` has now (0 once it resigned)."""
    p = state.player(seat)
    return 0 if p.resigned else sum(1 for s in state.settlers.values() if s.seat == seat)


def _ext(state: GameState) -> dict[str, Any]:
    return state.ext.setdefault(EXT_KEY, {"holder": None, "population": {}})


def populations(state: GameState) -> dict[int, int]:
    """Last computed population per seat (read-only)."""
    return {int(k): v for k, v in state.ext.get(EXT_KEY, {}).get("population", {}).items()}


def holder(state: GameState) -> int | None:
    return state.ext.get(EXT_KEY, {}).get("holder")


@after_step(order=ORDER)
def update_population(state: GameState, now_ms: int) -> list[Event]:
    if not active(state) or state.phase == "finished":
        return []
    cfg = state.settings.settlers.largest_population
    new = {p.seat: population(state, p.seat) for p in state.players}
    old_holder = holder(state)
    new_holder = longest_road.next_holder(old_holder, new, cfg.min)
    if new == populations(state) and new_holder == old_holder:
        return []
    ext = _ext(state)
    ext["population"] = {str(s): n for s, n in new.items()}
    ext["holder"] = new_holder
    events: list[Event] = [LargestPopulation(at=now_ms, seat=new_holder, previous=old_holder, population=new)]
    if new_holder == old_holder or cfg.points == 0:
        return events
    if old_holder is not None:
        state.player(old_holder).points -= cfg.points
        events.append(victory.points_changed(state, old_holder, now_ms))
    if new_holder is not None:
        state.player(new_holder).points += cfg.points
        events.append(victory.points_changed(state, new_holder, now_ms))
    return events


def state_view(state: GameState, viewer: int | None) -> dict[str, Any]:
    """Public: the holder and each seat's settler count ({} when the award is not played)."""
    if not active(state):
        return {}
    lp = state.ext.get(EXT_KEY, {})
    return {"holder": lp.get("holder"), "population": dict(lp.get("population", {}))}


register_state_extension(EXT_KEY, state_view)
