"""Robber (WP7): sevens, random steal percentage, random neighbour move.

:func:`on_seven` is called by dice when the roll equals ``settings.clock.robber_roll``
and ``settings.robber.enabled``. Nothing is produced on that roll.

1. Targets, in seat order: a player is a target when
   (``require_over_limit`` is off or the hand total > ``card_limit``) and
   (``require_adjacent`` is off or the player has a finished building on a vertex
   of the robber's hex). Adjacency is judged on the hex before the move
   (``adjacency_timing == "before_move"``) or after it (``"after_move"``, stage 3).
2. Each target loses ``steal_pct`` % of its hand total, rounded per
   ``steal_rounding`` (integer maths), drawn one card at a time uniformly from the
   hand with ``state.rng``. Stolen cards go to the bank when ``stolen_to_bank``
   (else they leave the game). Per target with a non-zero loss: ``RobberStole``
   (private) then ``Hand`` (private).
3. ``move_on_seven == "random_neighbour"``: the robber moves to a random
   neighbouring hex chosen from :func:`legal_neighbours` (land hexes; deserts only
   with ``may_enter_desert``; fishing grounds only with ``may_enter_fishing``; other
   sea never). With no legal neighbour it stays. ``RobberMoved`` is emitted in both
   cases (``from_hex == to_hex`` when it stayed). Other ``move_on_seven`` values
   (stage 3) leave the robber where it is and emit nothing.

Event order (before_move): ``RobberStole``, ``Hand`` per target, then ``RobberMoved``.
Later: knight moves (``move(by=seat, max_dist)``).
"""
from __future__ import annotations

from engine.events import Event, Hand, RobberMoved, RobberStole
from engine.settings.enums import (
    AdjacencyTiming,
    MoveOnSeven,
    Resource,
    Rounding,
    Terrain,
)
from engine.state import GameState

__all__ = ["legal_neighbours", "move_random", "on_seven", "steal_count", "steal_random", "targets"]


def _adjacent_seats(state: GameState, hex_id: int | None) -> set[int]:
    if hex_id is None:
        return set()
    seats: set[int] = set()
    for v in state.board.board.hex_vertices[hex_id]:
        b = state.buildings.get(v)
        if b is not None:
            seats.add(b.seat)
    return seats


def targets(state: GameState, hex_id: int | None) -> list[int]:
    """Seats the robber steals from, judged with the robber on ``hex_id``."""
    rs = state.settings.robber
    adjacent = _adjacent_seats(state, hex_id) if rs.require_adjacent else set()
    out: list[int] = []
    for p in state.players:
        if rs.require_over_limit and p.hand_count <= rs.card_limit:
            continue
        if rs.require_adjacent and p.seat not in adjacent:
            continue
        out.append(p.seat)
    return out


def steal_count(state: GameState, hand_total: int) -> int:
    """Cards the robber takes from a hand of ``hand_total`` cards."""
    rs = state.settings.robber
    num = hand_total * rs.steal_pct
    if rs.steal_rounding is Rounding.CEIL:
        return min(hand_total, -(-num // 100))
    return num // 100


def steal_random(state: GameState, seat: int, count: int) -> dict[Resource, int]:
    """Remove ``count`` uniformly random cards from ``seat``'s hand (one at a time).
    Returns the non-zero losses in resource order. Does not touch the bank."""
    hand = state.players[seat].hand
    lost: dict[Resource, int] = {}
    for _ in range(count):
        total = sum(hand.values())
        if total <= 0:
            break
        pick = state.rng.randbelow(total)
        for res in Resource:
            if pick < hand[res]:
                hand[res] -= 1
                lost[res] = lost.get(res, 0) + 1
                break
            pick -= hand[res]
    return {r: lost[r] for r in Resource if r in lost}


def _steal_from_targets(state: GameState, hex_id: int | None, now_ms: int) -> list[Event]:
    events: list[Event] = []
    to_bank = state.settings.robber.stolen_to_bank
    for seat in targets(state, hex_id):
        count = steal_count(state, state.players[seat].hand_count)
        if count <= 0:
            continue
        lost = steal_random(state, seat, count)
        if to_bank:
            for res, n in lost.items():
                state.bank[res] += n
        events.append(RobberStole(at=now_ms, seat=seat, lost=lost))
        events.append(Hand(at=now_ms, seat=seat, hand=dict(state.players[seat].hand)))
    return events


def legal_neighbours(state: GameState, hex_id: int) -> list[int]:
    """Neighbouring hexes the robber may move to from ``hex_id`` (board order)."""
    rs = state.settings.robber
    gb = state.board
    out: list[int] = []
    for n in gb.board.hex_neighbors[hex_id]:
        if gb.board.is_land(n):
            if gb.terrain[n] is Terrain.DESERT and not rs.may_enter_desert:
                continue
            out.append(n)
        elif n in gb.fishing and rs.may_enter_fishing:
            out.append(n)
    return out


def move_random(state: GameState, now_ms: int) -> list[Event]:
    """Move the robber to a random legal neighbour (or leave it); emit ``RobberMoved``."""
    start = state.robber_hex
    if start is None:
        return []
    options = legal_neighbours(state, start)
    dest = state.rng.choice(options) if options else start
    state.robber_hex = dest
    return [RobberMoved(at=now_ms, from_hex=start, to_hex=dest)]


def on_seven(state: GameState, now_ms: int) -> list[Event]:
    """Steal from the targets and move the robber (see the module docstring)."""
    rs = state.settings.robber
    if not rs.enabled:
        return []
    moves = rs.move_on_seven is MoveOnSeven.RANDOM_NEIGHBOUR
    if rs.adjacency_timing is AdjacencyTiming.AFTER_MOVE:
        events = move_random(state, now_ms) if moves else []
        return events + _steal_from_targets(state, state.robber_hex, now_ms)
    events = _steal_from_targets(state, state.robber_hex, now_ms)
    if moves:
        events += move_random(state, now_ms)
    return events
