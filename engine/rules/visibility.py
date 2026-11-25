"""Growing sight and hidden numbers (WP21): keeps ``state.ext["visibility"]`` up to date.

* ``@after_step(order=150)`` :func:`update_visibility`, after every step:
  1. fog on (``visibility.map`` not ``open``): each seat's sight now
     (:func:`engine.sight.seat_sight`: around its buildings and roads, and its
     settlers while they reveal) is added to what it has seen. Newly seen hexes
     -> :class:`Revealed` for that seat, with the board there and the pieces
     standing on it;
  2. ``visibility.hidden_numbers``: each seat sees the token of every hex it
     discovers itself (:func:`engine.sight.discovered_numbers`: next to its own
     buildings, or under its settlers) from then on -> :class:`NumbersRevealed` for
     that seat (tokens of producing hexes and fishing grounds only).

* ``@after_step(order=950)`` :func:`lift_fog`, after victory: once the game is over
  every seat sees the whole island -> one last :class:`Revealed` per seat.

The hook only adds, so running it again with nothing changed emits nothing. Rules
and bots keep reading the full state; only the views (``engine.views``) and the
board message (``engine.sight.board_for``) leave out what a player has not seen.
"""
from __future__ import annotations

from typing import Any

from engine import sight
from engine.events import Event, NumbersRevealed, Revealed, Sight
from engine.game import after_step
from engine.state import GameState
from engine.views import pieces_view

__all__ = ["update_visibility", "lift_fog", "reveal", "VISIBILITY_ORDER", "LIFT_FOG_ORDER"]

VISIBILITY_ORDER = 150
LIFT_FOG_ORDER = 950   # after victory (900) has finished the game


def _record(state: GameState) -> dict[str, Any]:
    return state.ext.setdefault(sight.EXT_KEY, {})


def reveal(state: GameState, seat: int, hexes: set[int], now_ms: int,
           back: frozenset[int] = frozenset()) -> Revealed | None:
    """Add ``hexes`` to what ``seat`` has seen; the event for the new ones, if any.
    ``back``: hexes already seen that came back into sight (Live fog), whose pieces
    are sent again."""
    old = sight.seen_hexes(state, seat)
    new = hexes - old
    if not new and not back:
        return None
    seen = old | new
    if new:
        _record(state).setdefault("seen", {})[str(seat)] = sorted(seen)
    board = sight.board_parts(state.board, new, seen, sight.shown_numbers(state, seat))
    pieces = pieces_view(state, -1, frozenset(new) | back)
    if pieces["robber"] is None:
        del pieces["robber"]
    return Revealed(at=now_ms, seat=seat, board=board, pieces=pieces)


def _numbers(state: GameState) -> dict[str, list[int]]:
    rec = _record(state)
    if not isinstance(rec.get("numbers"), dict):   # games saved before numbers were per player
        old = rec.get("numbers", [])
        rec["numbers"] = {str(p.seat): sorted(old) for p in state.players} if old else {}
    return rec["numbers"]


def _show_numbers(state: GameState, seat: int, hexes: set[int], now_ms: int,
                  producing_only: bool = True) -> NumbersRevealed | None:
    """Show ``seat`` the tokens of ``hexes`` it does not see yet; the event, if any."""
    gb = state.board
    shown = sight.shown_numbers(state, seat)
    new = {h for h in hexes - shown
           if gb.token[h] is not None and (not producing_only or gb.hex_resource(h) is not None)}
    if not new:
        return None
    _numbers(state)[str(seat)] = sorted(shown | new)
    return NumbersRevealed(at=now_ms, seat=seat, tokens={h: int(gb.token[h]) for h in sorted(new)})  # type: ignore[arg-type]


@after_step(order=VISIBILITY_ORDER)
def update_visibility(state: GameState, now_ms: int) -> list[Event]:
    events: list[Event] = []
    if sight.numbers_hidden(state):
        for p in state.players:
            ev = _show_numbers(state, p.seat, sight.discovered_numbers(state, p.seat), now_ms)
            if ev is not None:
                events.append(ev)
    if sight.fog_on(state):
        for p in state.players:
            events += _update_seat(state, p.seat, now_ms)
    return events


def _update_seat(state: GameState, seat: int, now_ms: int) -> list[Event]:
    now = sight.seat_sight(state, seat)
    sights = _record(state).setdefault("sight", {})
    before = set(sights.get(str(seat), ()))
    live = sight.live_fog(state)
    back = frozenset((now - before) & sight.seen_hexes(state, seat)) if live else frozenset()
    events: list[Event] = []
    rev = reveal(state, seat, now, now_ms, back)
    if rev is not None:
        events.append(rev)
    if live:
        _remember(state, seat, now)
    if now != before:
        sights[str(seat)] = sorted(now)
        events.append(Sight(at=now_ms, seat=seat, in_sight=sorted(now)))
    return events


def _remember(state: GameState, seat: int, hexes: set[int]) -> None:
    """Live fog: note other players' buildings and roads on ``hexes`` as ``seat`` sees them now."""
    gb = state.board
    mem = _record(state).setdefault("memory", {}).setdefault(str(seat), {"b": {}, "r": {}})
    for v in sight.seen_vertices(gb, hexes):
        b = state.buildings.get(v)
        if b is not None and b.seat != seat:
            mem["b"][str(v)] = [b.seat, b.kind.value]
        else:
            mem["b"].pop(str(v), None)
    for e in sight.seen_edges(gb, hexes):
        s = state.roads.get(e)
        if s is not None and s != seat:
            mem["r"][str(e)] = s
        else:
            mem["r"].pop(str(e), None)


@after_step(order=LIFT_FOG_ORDER)
def lift_fog(state: GameState, now_ms: int) -> list[Event]:
    """When the game is over, show every seat the whole island (and every number)."""
    if state.phase != "finished" or not sight.fog_on(state):
        return []
    gb = state.board
    everything = set(range(len(gb.board.hexes)))
    events: list[Event] = []
    if sight.numbers_hidden(state):
        for p in state.players:
            ev = _show_numbers(state, p.seat, everything, now_ms, producing_only=False)
            if ev is not None:
                events.append(ev)
    for p in state.players:
        back = frozenset(everything) if sight.live_fog(state) else frozenset()
        rev = reveal(state, p.seat, everything, now_ms, back)
        if rev is not None:
            events.append(rev)
    return events
