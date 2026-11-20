"""Growing sight and hidden numbers (WP21): keeps ``state.ext["visibility"]`` up to date.

* ``@after_step(order=150)`` :func:`update_visibility`, after every step:
  1. fog on (``visibility.map`` not ``open``): each seat's sight now
     (:func:`engine.sight.seat_sight`: around its buildings and roads, and its
     settlers while they reveal) is added to what it has seen. Newly seen hexes
     -> :class:`Revealed` for that seat, with the board there and the pieces
     standing on it;
  2. ``visibility.hidden_numbers``: every hex next to a building shows its token
     from then on -> :class:`NumbersRevealed` (tokens of producing hexes and
     fishing grounds only).

* ``@after_step(order=950)`` :func:`lift_fog`, after victory: once the game is over
  every seat sees the whole island -> one last :class:`Revealed` per seat.

The hook only adds, so running it again with nothing changed emits nothing. Rules
and bots keep reading the full state; only the views (``engine.views``) and the
board message (``engine.sight.board_for``) leave out what a player has not seen.
"""
from __future__ import annotations

from typing import Any

from engine import sight
from engine.events import Event, NumbersRevealed, Revealed
from engine.game import after_step
from engine.state import GameState
from engine.views import pieces_view

__all__ = ["update_visibility", "lift_fog", "reveal", "VISIBILITY_ORDER", "LIFT_FOG_ORDER"]

VISIBILITY_ORDER = 150
LIFT_FOG_ORDER = 950   # after victory (900) has finished the game


def _record(state: GameState) -> dict[str, Any]:
    return state.ext.setdefault(sight.EXT_KEY, {})


def reveal(state: GameState, seat: int, hexes: set[int], now_ms: int) -> Revealed | None:
    """Add ``hexes`` to what ``seat`` has seen; the event for the new ones, if any."""
    old = sight.seen_hexes(state, seat)
    new = hexes - old
    if not new:
        return None
    seen = old | new
    _record(state).setdefault("seen", {})[str(seat)] = sorted(seen)
    board = sight.board_parts(state.board, new, seen, sight.shown_numbers(state))
    pieces = pieces_view(state, -1, frozenset(new))
    if pieces["robber"] is None:
        del pieces["robber"]
    return Revealed(at=now_ms, seat=seat, board=board, pieces=pieces)


def _reveal_numbers(state: GameState, now_ms: int) -> NumbersRevealed | None:
    gb = state.board
    shown = set(_record(state).get("numbers", ()))
    near = {h for v in state.buildings for h in gb.board.vertex_hexes[v]}
    new = {h for h in near - shown if gb.token[h] is not None and gb.hex_resource(h) is not None}
    if not new:
        return None
    _record(state)["numbers"] = sorted(shown | new)
    return NumbersRevealed(at=now_ms, tokens={h: int(gb.token[h]) for h in sorted(new)})  # type: ignore[arg-type]


@after_step(order=VISIBILITY_ORDER)
def update_visibility(state: GameState, now_ms: int) -> list[Event]:
    events: list[Event] = []
    if sight.numbers_hidden(state):
        ev = _reveal_numbers(state, now_ms)
        if ev is not None:
            events.append(ev)
    if sight.fog_on(state):
        for p in state.players:
            rev = reveal(state, p.seat, sight.seat_sight(state, p.seat), now_ms)
            if rev is not None:
                events.append(rev)
    return events


@after_step(order=LIFT_FOG_ORDER)
def lift_fog(state: GameState, now_ms: int) -> list[Event]:
    """When the game is over, show every seat the whole island (and every number)."""
    if state.phase != "finished" or not sight.fog_on(state):
        return []
    gb = state.board
    everything = set(range(len(gb.board.hexes)))
    events: list[Event] = []
    if sight.numbers_hidden(state):
        shown = set(_record(state).get("numbers", ()))
        new = {h for h in everything - shown if gb.token[h] is not None}
        _record(state)["numbers"] = sorted(everything)
        if new:
            events.append(NumbersRevealed(at=now_ms, tokens={h: int(gb.token[h]) for h in sorted(new)}))  # type: ignore[arg-type]
    for p in state.players:
        rev = reveal(state, p.seat, everything, now_ms)
        if rev is not None:
            events.append(rev)
    return events
