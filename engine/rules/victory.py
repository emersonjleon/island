"""Victory (WP7): points, target, game over.

* ``@connect(SIG_BUILT)`` (:func:`on_built`): a settlement adds
  ``settings.victory.building_points.settlement`` to the cached ``player.points``,
  a city adds ``building_points.city - building_points.settlement`` (it replaces
  its settlement); roads add nothing. Emits ``Points`` when the score changed.
  If the player now has at least ``settings.victory.target`` points the game ends
  at once (:func:`finish`), so ``game.advance`` fires no further timer, not even
  ones due in the same call; ``GameOver`` follows from the after-step hook.
* ``@after_step(order=900)`` (:func:`check_victory`): if the game is not finished
  and some player has reached the target (points changed by any other means),
  finish it; then emit ``GameOver`` exactly once (tracked in
  ``state.ext["victory"]["announced"]``).

Finishing sets ``phase = "finished"``, ``winner``, ``finished_at = now`` and cancels
the dice timer (``roll_timer_id`` and ``next_roll_at`` become None).

Winner rule: the first player to reach the target. When several players are at or
above the target in the same check (only possible via :func:`check_victory`), the
one with the most points wins, ties broken by the lowest seat. Players who resigned
(:mod:`engine.rules.resign`) can no longer win; resign ends the game itself with
``finish(..., reason="resign")``.
"""
from __future__ import annotations

from typing import Any

from engine.events import Event, GameOver, Points
from engine.game import SIG_BUILT, after_step, connect
from engine.rules import stats
from engine.settings.enums import BuildKind
from engine.state import GameState

__all__ = [
    "AFTER_STEP_ORDER",
    "BUILT_ORDER",
    "EXT_KEY",
    "building_points",
    "check_victory",
    "finish",
    "leader",
    "leader_at_target",
    "on_built",
    "points_changed",
]

BUILT_ORDER = 100
AFTER_STEP_ORDER = 900
EXT_KEY = "victory"


def building_points(state: GameState, kind: BuildKind) -> int:
    """Points a newly placed piece adds (a city replaces its settlement)."""
    bp = state.settings.victory.building_points
    if kind is BuildKind.SETTLEMENT:
        return bp.settlement
    if kind is BuildKind.CITY:
        return bp.city - bp.settlement
    if kind is BuildKind.MEGACITY:
        return bp.megacity - bp.city
    return 0


def leader(state: GameState, min_points: int = 0) -> int | None:
    """Seat with the most points among the players still in the game with at least
    ``min_points`` (lowest seat on ties), or None."""
    best: int | None = None
    for p in state.players:
        if p.resigned or p.points < min_points:
            continue
        if best is None or p.points > state.players[best].points:
            best = p.seat
    return best


def leader_at_target(state: GameState) -> int | None:
    """Seat with the most points among those at or above the target (lowest seat on ties)."""
    return leader(state, state.settings.victory.target)


def finish(state: GameState, winner: int | None, now_ms: int, reason: str = "target") -> None:
    """End the game now (idempotent: does nothing if already finished)."""
    if state.phase == "finished":
        return
    _ext(state)["reason"] = reason
    state.phase = "finished"
    state.winner = winner
    state.finished_at = now_ms
    state.timers.cancel(state.roll_timer_id)
    state.roll_timer_id = None
    state.next_roll_at = None


def points_changed(state: GameState, seat: int, now_ms: int) -> Points:
    """Call after changing ``seat``'s points: records the score history and returns the event."""
    points = state.player(seat).points
    stats.record_points(state, seat, now_ms, points)
    return Points(at=now_ms, seat=seat, points=points)


def _ext(state: GameState) -> dict[str, Any]:
    return state.ext.setdefault(EXT_KEY, {})


@connect(SIG_BUILT, order=BUILT_ORDER)
def on_built(state: GameState, now_ms: int, *, seat: int, kind: BuildKind, target: int, setup: bool,
             construction: int, **_: Any) -> list[Event]:
    delta = building_points(state, BuildKind(kind))
    if delta == 0:
        return []
    player = state.player(seat)
    player.points += delta
    if player.points >= state.settings.victory.target and not player.resigned:
        finish(state, seat, now_ms)
    return [points_changed(state, seat, now_ms)]


@after_step(order=AFTER_STEP_ORDER)
def check_victory(state: GameState, now_ms: int) -> list[Event]:
    if state.phase != "finished":
        leader = leader_at_target(state)
        if leader is None:
            return []
        finish(state, leader, now_ms)
    ext = _ext(state)
    if ext.get("announced"):
        return []
    ext["announced"] = True
    at = state.finished_at if state.finished_at is not None else now_ms
    reason = "resign" if ext.get("reason") == "resign" else "target"
    return [GameOver(at=at, winner=state.winner, points={p.seat: p.points for p in state.players}, reason=reason)]
