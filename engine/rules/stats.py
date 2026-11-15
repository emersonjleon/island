"""Game statistics (stage 2): how each player's score grew, and what the dice paid them.

Kept in ``state.ext["stats"]`` (JSON-safe, string seat keys):

* ``timeline``: seat -> ``[[game_ms, points], ...]``, starting with ``[0, 0]`` and one
  entry whenever the score changed (:func:`record_points`, called through
  :func:`engine.rules.victory.points_changed` by every rule that changes points);
* ``produced``: seat -> resource -> cards received from dice rolls (``SIG_PRODUCED``).

Projected as ``state.stats``. A player's timeline is shown where their points are
(their own, ``visibility.scores = shown``, or once the game is over); their
production where the production log shows it (their own, ``production_log = all``,
or once the game is over). The per-source split of the points is worked out by the
client from the board and the awards.
"""
from __future__ import annotations

from typing import Any

from engine.events import Event
from engine.game import SIG_PRODUCED, connect, on_new_game
from engine.settings.enums import ProductionLog, Resource, ScoreVisibility
from engine.state import GameState
from engine.views import register_state_extension

__all__ = ["EXT_KEY", "start", "on_produced", "produced", "record_points", "state_view", "timeline"]

EXT_KEY = "stats"


def _ext(state: GameState) -> dict[str, Any]:
    ext = state.ext.setdefault(EXT_KEY, {})
    ext.setdefault("timeline", {})
    ext.setdefault("produced", {})
    return ext


def timeline(state: GameState, seat: int) -> list[list[int]]:
    return [list(e) for e in state.ext.get(EXT_KEY, {}).get("timeline", {}).get(str(seat), [])]


def produced(state: GameState, seat: int) -> dict[str, int]:
    return dict(state.ext.get(EXT_KEY, {}).get("produced", {}).get(str(seat), {}))


@on_new_game()
def start(state: GameState, now_ms: int) -> list[Event]:
    for p in state.players:
        record_points(state, p.seat, now_ms, p.points)
    return []


def record_points(state: GameState, seat: int, now_ms: int, points: int) -> None:
    """Add ``[now_ms, points]`` to ``seat``'s timeline unless the score is unchanged."""
    line = _ext(state)["timeline"].setdefault(str(seat), [])
    if not line or line[-1][1] != points:
        line.append([now_ms, points])


@connect(SIG_PRODUCED)
def on_produced(state: GameState, now_ms: int, *, gains: dict[int, dict[Resource, int]], **_: Any) -> list[Event]:
    totals = _ext(state)["produced"]
    for seat, got in gains.items():
        mine = totals.setdefault(str(seat), {})
        for r, n in got.items():
            key = Resource(r).value
            mine[key] = mine.get(key, 0) + n
    return []


def state_view(state: GameState, viewer: int | None) -> dict[str, Any]:
    vis = state.settings.visibility
    over = state.phase == "finished"
    out: dict[str, Any] = {"timeline": {}, "produced": {}}
    for p in state.players:
        own = viewer is not None and viewer == p.seat
        if own or over or vis.scores is ScoreVisibility.SHOWN:
            out["timeline"][str(p.seat)] = timeline(state, p.seat)
        if own or over or vis.production_log is not ProductionLog.OWN:
            out["produced"][str(p.seat)] = produced(state, p.seat)
    return out


register_state_extension("stats", state_view)
