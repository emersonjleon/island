"""Largest Population (ages): an award, like the Longest Road, for the biggest population.

A seat's population is ``per_settlement`` per settlement, ``per_city`` per city and
``per_megacity`` per megacity (``settings.ages.largest_population``). Only with ages on.

* ``@connect(SIG_BUILT)`` (:func:`on_built`): after a settlement, city or megacity,
  recompute every population and the holder. Emits ``LargestPopulation`` when a
  population or the holder changed, and ``Points`` for each seat whose score changed.
  A player who reaches the target this way wins at once.

Award rules (the same as the Longest Road, :func:`engine.rules.longest_road.next_holder`):
a seat needs at least ``min``; the holder keeps it while tied; another seat takes it
only with a strictly larger population; the holder gets ``points`` extra points.

State: ``state.ext["largest_population"] = {"holder": seat | None, "population": {"<seat>": n}}``.
"""
from __future__ import annotations

from typing import Any

from engine.events import Event, LargestPopulation
from engine.game import SIG_BUILT, connect
from engine.rules import age_state, longest_road, victory
from engine.settings.enums import BuildKind
from engine.state import GameState

__all__ = ["BUILT_ORDER", "EXT_KEY", "population", "populations", "holder", "on_built"]

BUILT_ORDER = longest_road.BUILT_ORDER + 10
EXT_KEY = "largest_population"


def population(state: GameState, seat: int) -> int:
    cfg = state.settings.ages.largest_population
    per = {BuildKind.SETTLEMENT: cfg.per_settlement, BuildKind.CITY: cfg.per_city,
           BuildKind.MEGACITY: cfg.per_megacity}
    return sum(per.get(b.kind, 0) for b in state.buildings.values() if b.seat == seat)


def _ext(state: GameState) -> dict[str, Any]:
    return state.ext.setdefault(EXT_KEY, {"holder": None, "population": {}})


def populations(state: GameState) -> dict[int, int]:
    """Last computed population per seat (read-only)."""
    return {int(k): v for k, v in state.ext.get(EXT_KEY, {}).get("population", {}).items()}


def holder(state: GameState) -> int | None:
    return state.ext.get(EXT_KEY, {}).get("holder")


@connect(SIG_BUILT, order=BUILT_ORDER)
def on_built(state: GameState, now_ms: int, *, seat: int, kind: BuildKind, target: int, setup: bool,
             construction: int, **_: Any) -> list[Event]:
    if not age_state.enabled(state) or BuildKind(kind) is BuildKind.ROAD or state.phase == "finished":
        return []
    ext = _ext(state)
    cfg = state.settings.ages.largest_population
    new = {p.seat: population(state, p.seat) for p in state.players}
    old_holder = ext["holder"]
    new_holder = longest_road.next_holder(old_holder, new, cfg.min)
    if new == populations(state) and new_holder == old_holder:
        return []
    ext["population"] = {str(s): n for s, n in new.items()}
    ext["holder"] = new_holder
    events: list[Event] = [LargestPopulation(at=now_ms, seat=new_holder, previous=old_holder, population=new)]
    if new_holder == old_holder or cfg.points == 0:
        return events
    if old_holder is not None:
        state.player(old_holder).points -= cfg.points
        events.append(victory.points_changed(state, old_holder, now_ms))
    if new_holder is not None:
        p = state.player(new_holder)
        p.points += cfg.points
        events.append(victory.points_changed(state, new_holder, now_ms))
        if p.points >= state.settings.victory.target and not p.resigned:
            victory.finish(state, new_holder, now_ms)
    return events
