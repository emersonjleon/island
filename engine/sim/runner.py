"""Headless game runner and replay (WP8).

:class:`Simulation` drives a game with bots under a manual clock: it jumps
straight to the next interesting time (a timer, or the next bot "think" tick),
fires timers with ``game.advance``, lets every bot act, and records each
**accepted** command as a :class:`CommandRecord` -- the same log the game host
persists. :func:`replay` rebuilds a game from settings, seats, seed and that log
alone; :func:`resume` continues from a ``codec.dump`` snapshot.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from engine import codec, game
from engine.board.model import GeneratedBoard
from engine.errors import RuleError
from engine.events import Event
from engine.settings.models import GameSettings
from engine.sim import invariants
from engine.sim.bots import Bot, make_bot
from engine.state import GameState, SeatInfo

__all__ = ["CommandRecord", "Simulation", "SimResult", "replay", "resume", "run_game"]


@dataclass(frozen=True)
class CommandRecord:
    """One accepted command: game time, seat and the raw intent payload."""
    at: int
    seat: int
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "seat": self.seat, "payload": self.payload}


@dataclass
class SimResult:
    state: GameState
    log: list[CommandRecord]
    events: int
    rejects: dict[str, int] = field(default_factory=dict)
    steps: int = 0

    @property
    def finished(self) -> bool:
        return self.state.phase == "finished"

    @property
    def rolls(self) -> int:
        return len(self.state.dice_history)


class Simulation:
    """Run ``bots`` (one per seat, in seat order) against a new game.

    ``think_ms``: bots act every ``think_ms`` of game time (and at time 0).
    ``check``: verify :mod:`engine.sim.invariants` after every step.
    ``on_events``: optional callback ``fn(events)`` for every event batch.
    """

    def __init__(self, settings: GameSettings, seats: list[SeatInfo], seed: int, bots: Sequence[Bot],
                 board: GeneratedBoard | None = None, think_ms: int = 1000, check: bool = True,
                 on_events: Any = None) -> None:
        if len(bots) != len(seats):
            raise ValueError("one bot per seat")
        self.bots = list(bots)
        self.think_ms = think_ms
        self.check = check
        self.on_events = on_events
        self.state, events = game.new_game(settings, seats, seed, board=board)
        self.totals = invariants.resource_totals(self.state)
        self.log: list[CommandRecord] = []
        self.rejects: dict[str, int] = {}
        self.events = 0
        self.steps = 0
        self.next_think = 0
        self._emit(events)

    def _emit(self, events: list[Event]) -> None:
        self.events += len(events)
        if self.on_events is not None and events:
            self.on_events(events)
        if self.check:
            invariants.check(self.state, self.totals)

    def step(self) -> None:
        """Advance to the next timer or think tick and let bots act there."""
        st = self.state
        wake = game.next_wakeup(st)
        t = self.next_think if wake is None else min(wake, self.next_think)
        self._emit(game.advance(st, t))
        self.steps += 1
        if t < self.next_think or st.phase == "finished":
            return
        self.next_think = t + self.think_ms
        for bot in self.bots:
            for intent in bot.decide(st):
                if st.phase == "finished":
                    return
                self._emit(game.advance(st, t))
                try:
                    events = game.apply(st, bot.seat, intent, t)
                except RuleError as exc:
                    self.rejects[exc.code] = self.rejects.get(exc.code, 0) + 1
                    continue
                self.log.append(CommandRecord(t, bot.seat, intent))
                self._emit(events)

    def run(self, max_ms: int) -> SimResult:
        """Step until the game finishes or game time passes ``max_ms``."""
        while self.state.phase != "finished" and self.state.now_ms < max_ms:
            self.step()
        return SimResult(self.state, self.log, self.events, self.rejects, self.steps)


def run_game(settings: GameSettings, seats: list[SeatInfo], seed: int, bot_kinds: Iterable[str],
             max_ms: int, board: GeneratedBoard | None = None, think_ms: int = 1000,
             check: bool = True) -> SimResult:
    """Convenience: one bot of each kind per seat (bot seeds derived from ``seed``)."""
    bots = [make_bot(k, i, seed * 1000 + i) for i, k in enumerate(bot_kinds)]
    return Simulation(settings, seats, seed, bots, board=board, think_ms=think_ms, check=check).run(max_ms)


def _play(state: GameState, log: Iterable[CommandRecord], until_ms: int | None) -> GameState:
    for rec in log:
        game.advance(state, rec.at)
        game.apply(state, rec.seat, rec.payload, rec.at)
    if until_ms is not None and state.phase != "finished":
        game.advance(state, until_ms)
    return state


def replay(settings: GameSettings, seats: list[SeatInfo], seed: int, log: Iterable[CommandRecord],
           until_ms: int | None = None, board: GeneratedBoard | None = None) -> GameState:
    """Rebuild a game from its command log (raises if a logged command is rejected)."""
    state, _ = game.new_game(settings, seats, seed, board=board)
    return _play(state, log, until_ms)


def resume(snapshot: dict[str, Any], log: Iterable[CommandRecord], until_ms: int | None = None) -> GameState:
    """Load a ``codec.dump`` snapshot and replay the commands logged after it."""
    return _play(codec.load(snapshot), log, until_ms)
