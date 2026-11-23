"""Resigning (stage 2): a player gives up and leaves the game for good.

``resign`` (no fields) from a player still in the game:

* their unfinished builds are cancelled (reason ``"resigned"``, refunded as usual)
  and their settlers leave the map;
* their whole hand (refunds included) goes back to the bank (development cards
  stay in their hand, unplayable);
* their roads and buildings stay on the board, still blocking spots, but no longer
  produce (:mod:`engine.rules.production`), and their points are frozen; they can
  no longer win (:mod:`engine.rules.victory`);
* ``game.apply`` rejects any later command of theirs (``game.resigned``).

Emits ``Hand`` (when the hand was not empty) and ``Resigned``. The game then ends
(``GameOver`` with ``reason = "resign"``, winner: the leader among the players still
in) when at most one player is left, or when the game had people and only computer
players (``user_id`` None) are left.
"""
from __future__ import annotations

from engine.commands import Resign
from engine.events import Event, Hand, Resigned
from engine.game import command_handler
from engine.rules import ages, construction, setup, victory
from engine.settings.enums import Resource
from engine.state import GameState

__all__ = ["active_seats", "game_should_end", "handle_resign"]

def active_seats(state: GameState) -> list[int]:
    """Seats of the players who have not resigned."""
    return [p.seat for p in state.players if not p.resigned]


def game_should_end(state: GameState) -> bool:
    """At most one player left, or only computer players left in a game that had people."""
    active = [p for p in state.players if not p.resigned]
    if len(active) <= 1:
        return True
    had_people = any(p.info.user_id is not None for p in state.players)
    return had_people and all(p.info.user_id is None for p in active)


@command_handler("resign")
def handle_resign(state: GameState, seat: int, cmd: Resign, now_ms: int) -> list[Event]:
    p = state.player(seat)
    p.resigned_at = now_ms
    events: list[Event] = []
    for cid in sorted(state.constructions):
        c = state.constructions.get(cid)
        if c is not None and c.seat == seat:
            events += construction.cancel_construction(state, c, "resigned", now_ms)
    events += ages.cancel_advance(state, seat, "resigned", now_ms)
    events += setup.remove_settlers(state, seat, now_ms)
    returned = {r: p.hand[r] for r in Resource if p.hand[r] > 0}
    for r, n in returned.items():
        state.bank[r] += n
        p.hand[r] = 0
    if returned:
        events.append(Hand(at=now_ms, seat=seat, hand=dict(p.hand)))
    events.append(Resigned(at=now_ms, seat=seat, returned=returned))
    if game_should_end(state):
        victory.finish(state, victory.leader(state), now_ms, reason="resign")
    return events
