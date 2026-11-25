"""Ages (WP26, docs/AGES_DESIGN.md): each player advances from age I to II and III.

* ``advance_age`` command (``ages.enabled``): a player whose setup is done, not
  already researching, below the last age, with the step's required cities
  (megacities count) and points, pays ``ages.ageN.cost`` into escrow and researches
  for ``ages.ageN.time_ms`` (0: at once). Emits ``AgeAdvanceStarted`` then ``Hand``.
* ``cancel_age`` command: refunds ``build.refund_pct`` of the escrow (floor per
  resource, the rest to the bank), like a construction. Resigning cancels too
  (reason ``"resigned"``). Emits ``AgeAdvanceCancelled`` (+ ``Hand`` if refunded).
* ``age_done`` timer: the escrow goes to the bank, the player is in the new age and
  gains ``bonus.points`` (reaching the target ends the game). Emits ``AgeReached``
  then ``Points``.

What an age changes (helpers in :mod:`engine.rules.age_state`): constructions
locked behind ``ages.unlock`` (``age.locked``), the safe hand size on a 7
(``bonus.card_limit``, adds up), extra fish per building on a producing fishing
ground (``bonus.fish_per_fishing_building``, adds up) and build times
(``bonus.build_time_pct`` of the highest age). Ages are public, even with fog.

Reject codes: ``age.disabled``, ``age.setup_not_done``, ``age.in_progress``,
``age.max``, ``age.need_cities`` {need, have}, ``age.need_points`` {need, have},
``age.cannot_afford`` {missing}, ``age.not_advancing``.

Invariant: bank + hands + escrow (construction and age) is constant per resource.
"""
from __future__ import annotations

from typing import Any

from engine.commands import AdvanceAge, CancelAge
from engine.errors import RuleError
from engine.events import AgeAdvanceCancelled, AgeAdvanceStarted, AgeReached, Event, Hand
from engine.game import TIMER_AGE_DONE, command_handler, timer_handler
from engine.rules import victory
from engine.rules.age_state import LAST_AGE, advancing, age_of, city_count, enabled, ext, step
from engine.rules.placement import missing_resources
from engine.scheduler import Timer
from engine.settings.enums import Resource
from engine.state import GameState
from engine.views import register_state_extension

__all__ = ["advance_error", "handle_advance", "handle_cancel", "cancel_advance", "age_done", "state_view"]


def _cost(state: GameState, age: int) -> dict[Resource, int]:
    return {r: n for r, n in step(state, age).cost.items() if n}


def advance_error(state: GameState, seat: int) -> RuleError | None:
    """Why ``seat`` cannot start the next age now, or None."""
    if not enabled(state):
        return RuleError("age.disabled", {})
    p = state.player(seat)
    if not p.setup_done:
        return RuleError("age.setup_not_done", {})
    if advancing(state, seat) is not None:
        return RuleError("age.in_progress", {})
    current = age_of(state, seat)
    if current >= LAST_AGE:
        return RuleError("age.max", {"age": current})
    req = step(state, current + 1).requires
    cities = city_count(state, seat)
    if cities < req.cities:
        return RuleError("age.need_cities", {"need": req.cities, "have": cities})
    if p.points < req.points:
        return RuleError("age.need_points", {"need": req.points, "have": p.points})
    missing = missing_resources(p.hand, _cost(state, current + 1))
    if missing:
        return RuleError("age.cannot_afford", {"missing": missing})
    return None


def _hand(state: GameState, seat: int, now_ms: int) -> Hand:
    return Hand(at=now_ms, seat=seat, hand=dict(state.player(seat).hand))


@command_handler("advance_age")
def handle_advance(state: GameState, seat: int, cmd: AdvanceAge, now_ms: int) -> list[Event]:
    err = advance_error(state, seat)
    if err is not None:
        raise err
    age = age_of(state, seat) + 1
    cost = _cost(state, age)
    p = state.player(seat)
    for r, n in cost.items():
        p.hand[r] -= n
    done = now_ms + step(state, age).time_ms
    research: dict[str, Any] = {"age": age, "t0": now_ms, "t1": done, "paid": {r.value: n for r, n in cost.items()},
                                "timer": None}
    ext(state)["advancing"][str(seat)] = research
    events: list[Event] = [AgeAdvanceStarted(at=now_ms, seat=seat, age=age, t0=now_ms, t1=done, paid=dict(cost)),
                           _hand(state, seat, now_ms)]
    if done == now_ms:
        return events + _reach(state, seat, now_ms)
    research["timer"] = state.timers.schedule(done, TIMER_AGE_DONE, {"seat": seat})
    return events


def cancel_advance(state: GameState, seat: int, reason: str, now_ms: int) -> list[Event]:
    """Stop ``seat``'s research (if any): refund ``build.refund_pct``, the rest to the bank."""
    research = ext(state)["advancing"].pop(str(seat), None)
    if research is None:
        return []
    state.timers.cancel(research.get("timer"))
    p = state.player(seat)
    pct = state.settings.build.refund_pct
    refund: dict[Resource, int] = {}
    for key, n in research["paid"].items():
        r = Resource(key)
        back = n * pct // 100
        p.hand[r] += back
        state.bank[r] += n - back
        if back:
            refund[r] = back
    events: list[Event] = [AgeAdvanceCancelled(at=now_ms, seat=seat, age=research["age"], reason=reason,
                                               refund=refund)]
    if refund:
        events.append(_hand(state, seat, now_ms))
    return events


@command_handler("cancel_age")
def handle_cancel(state: GameState, seat: int, cmd: CancelAge, now_ms: int) -> list[Event]:
    if advancing(state, seat) is None:
        raise RuleError("age.not_advancing", {})
    return cancel_advance(state, seat, "cancelled", now_ms)


def _reach(state: GameState, seat: int, now_ms: int) -> list[Event]:
    e = ext(state)
    research = e["advancing"].pop(str(seat))
    for key, n in research["paid"].items():
        state.bank[Resource(key)] += n
    age = research["age"]
    e["age"][str(seat)] = age
    e["reached"].setdefault(str(seat), {})[str(age)] = now_ms
    events: list[Event] = [AgeReached(at=now_ms, seat=seat, age=age)]
    bonus = step(state, age).bonus.points
    if bonus:
        p = state.player(seat)
        p.points += bonus
        if p.points >= state.settings.victory.target and not p.resigned:
            victory.finish(state, seat, now_ms)
        events.append(victory.points_changed(state, seat, now_ms))
    return events


@timer_handler(TIMER_AGE_DONE)
def age_done(state: GameState, timer: Timer, now_ms: int) -> list[Event]:
    seat = int(timer.payload["seat"])
    research = advancing(state, seat)
    if research is None or research.get("timer") != timer.id:
        return []
    return _reach(state, seat, now_ms)


def state_view(state: GameState, viewer: int | None) -> dict[str, Any]:
    """Public: each player's age, research in progress and when each age was reached."""
    if not enabled(state):
        return {}
    e = state.ext.get("ages", {})
    players = {}
    for p in state.players:
        research = advancing(state, p.seat)
        players[str(p.seat)] = {
            "age": age_of(state, p.seat),
            "advancing": None if research is None else {k: research[k] for k in ("age", "t0", "t1")},
            "reached": dict(e.get("reached", {}).get(str(p.seat), {})),
        }
    return {"players": players}


register_state_extension("ages", state_view)
