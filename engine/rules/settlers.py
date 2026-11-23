"""Settlers variation (WP23): buying settlers, gathering, blocking the robber.

* ``buy_settler`` command, only when settlers stay after setup
  (``settlers.leave_after_setup`` off): a player whose setup is done, with fewer than
  :func:`settler_limit` settlers (``per_settlement`` per settlement + ``per_city`` per
  city or megacity, at least 1, capped by ``settlers.max``), pays ``economy.costs.settler`` to the bank; the new
  settler appears at ``vertex`` (one of the player's buildings) or, without one,
  at the player's building with the lowest vertex id (``settlers.spawn_at =
  own_building``). Emits ``Hand`` then ``SettlerLanded``.
* :func:`gather`, called by dice after production on every roll that is not the
  robber roll, when ``settlers.gather`` is on: a player's settlers are numbered by
  id (1st, 2nd, ...) and the i-th one gathers on the numbers
  ``settlers.gather_rolls[i % len]``. A settler at rest (not walking, not building)
  whose number came up takes ``settlers.gather_cards`` of each producing hex at its
  corner (fishing grounds count; the robber's hex does not). The bank pays what it
  holds, per resource in seat order. Emits ``SettlersGathered`` (when anyone
  gathered) and ``Hand`` per seat, and ``SIG_PRODUCED`` so the statistics count it.
* :func:`blocked_hexes`: with ``settlers.block_robber``, hexes with a settler on one
  of their corners, where the robber may not go (random moves and knights).

Reject codes of ``buy_settler``: ``settler.not_available``, ``settler.setup_not_done``, ``settler.max`` {max},
``settler.cannot_afford`` {missing}, ``settler.no_building``,
``settler.not_your_building`` {vertex}.
"""
from __future__ import annotations

from engine.commands import BuySettler
from engine.errors import RuleError
from engine.events import Event, Hand, SettlerLanded, SettlersGathered
from engine.game import SIG_PRODUCED, command_handler, emit
from engine.rules import age_state, movement
from engine.rules.placement import missing_resources
from engine.settings.enums import BuildKind, Resource
from engine.state import GameState, Settler

__all__ = ["buy_settler", "can_buy", "settler_limit", "gather", "gather_numbers", "blocked_hexes", "settler_at_work"]


# ------------------------------------------------------------------ buying
def _spawn_vertex(state: GameState, seat: int, wanted: int | None) -> int:
    own = sorted(v for v, b in state.buildings.items() if b.seat == seat)
    if wanted is not None:
        if wanted not in own:
            raise RuleError("settler.not_your_building", {"vertex": wanted})
        return wanted
    if not own:
        raise RuleError("settler.no_building", {})
    return own[0]


def settler_limit(state: GameState, seat: int) -> int:
    """How many settlers ``seat`` may have now."""
    ss = state.settings.settlers
    if ss.per_settlement == 0 and ss.per_city == 0:
        return ss.max
    allowed = sum(ss.per_settlement if b.kind == BuildKind.SETTLEMENT else ss.per_city
                  for b in state.buildings.values() if b.seat == seat)
    return min(ss.max, max(1, allowed))


def can_buy(state: GameState, seat: int) -> bool:
    """Whether ``seat`` may buy a settler now (ignoring where it would land)."""
    p = state.player(seat)
    ss = state.settings.settlers
    cost = {r: n for r, n in state.settings.economy.costs.settler.items() if n}
    return (not ss.leave_after_setup and p.setup_done and len(p.settler_ids) < settler_limit(state, seat)
            and not missing_resources(p.hand, cost))


@command_handler("buy_settler")
def buy_settler(state: GameState, seat: int, cmd: BuySettler, now_ms: int) -> list[Event]:
    p = state.player(seat)
    ss = state.settings.settlers
    if ss.leave_after_setup:
        raise RuleError("settler.not_available", {})
    if not p.setup_done:
        raise RuleError("settler.setup_not_done", {})
    limit = settler_limit(state, seat)
    if len(p.settler_ids) >= limit:
        raise RuleError("settler.max", {"max": limit})
    cost = {r: n for r, n in state.settings.economy.costs.settler.items() if n}
    missing = missing_resources(p.hand, cost)
    if missing:
        raise RuleError("settler.cannot_afford", {"missing": missing})
    vertex = _spawn_vertex(state, seat, cmd.vertex)
    for r, n in cost.items():
        p.hand[r] -= n
        state.bank[r] += n
    sid = state.next_id("settler")
    state.settlers[sid] = Settler(id=sid, seat=seat, vertex=vertex)
    p.settler_ids.append(sid)
    return [Hand(at=now_ms, seat=seat, hand=dict(p.hand)),
            SettlerLanded(at=now_ms, settler=sid, seat=seat, vertex=vertex)]


# ---------------------------------------------------------------- gathering
def gather_numbers(state: GameState, settler_id: int) -> list[int]:
    """The rolls on which ``settler_id`` gathers (its place among its player's settlers)."""
    s = state.settlers[settler_id]
    order = sorted(state.player(s.seat).settler_ids)
    rolls = state.settings.settlers.gather_rolls
    return list(rolls[order.index(settler_id) % len(rolls)])


def settler_at_work(state: GameState, settler_id: int) -> int | None:
    """The settler's corner when it can gather: at rest and not building; else None."""
    v = movement.settler_at_rest(state, settler_id)
    if v is None or any(c.builder == settler_id for c in state.constructions.values()):
        return None
    return v


def _owed(state: GameState, roll: int) -> tuple[dict[int, dict[Resource, int]], list[int]]:
    gb = state.board
    n = state.settings.settlers.gather_cards
    owed: dict[int, dict[Resource, int]] = {}
    who: list[int] = []
    for sid in sorted(state.settlers):
        s = state.settlers[sid]
        if state.player(s.seat).resigned or roll not in gather_numbers(state, sid):
            continue
        if not age_state.has_age(state, s.seat, state.settings.ages.settler_gather_age):
            continue
        v = settler_at_work(state, sid)
        if v is None:
            continue
        got = False
        for h in gb.board.vertex_hexes[v]:
            res = gb.hex_resource(h)
            if res is None or h == state.robber_hex or n <= 0:
                continue
            mine = owed.setdefault(s.seat, {})
            mine[res] = mine.get(res, 0) + n
            got = True
        if got:
            who.append(sid)
    return owed, who


def gather(state: GameState, roll: int, now_ms: int) -> list[Event]:
    if not state.settings.settlers.gather:
        return []
    owed, who = _owed(state, roll)
    gains: dict[int, dict[Resource, int]] = {}
    for seat in sorted(owed):
        for res in Resource:
            want = owed[seat].get(res, 0)
            n = min(want, state.bank[res])
            if n <= 0:
                continue
            state.bank[res] -= n
            state.players[seat].hand[res] += n
            gains.setdefault(seat, {})[res] = n
    if not gains:
        return []
    events: list[Event] = [SettlersGathered(at=now_ms, roll=roll, gains=gains, settlers=who)]
    events += [Hand(at=now_ms, seat=seat, hand=dict(state.players[seat].hand)) for seat in gains]
    return events + emit(state, SIG_PRODUCED, now_ms, gains=gains)


# ------------------------------------------------------------------ robber
def blocked_hexes(state: GameState) -> frozenset[int]:
    """Hexes the robber may not enter because a settler stands on one of their corners."""
    if not state.settings.settlers.block_robber:
        return frozenset()
    vh = state.board.board.vertex_hexes
    guard = state.settings.ages.settler_guard_age
    return frozenset(h for s in state.settlers.values() if age_state.has_age(state, s.seat, guard)
                     for h in vh[s.vertex])
