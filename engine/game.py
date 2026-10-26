"""Orchestrator: ``new_game`` / ``apply`` / ``advance`` / ``next_wakeup`` plus the handler registry.

Rule modules (``engine.rules.*``) plug in with decorators and never edit this file:

``@command_handler("build")``
    ``fn(state, seat, cmd, now_ms) -> list[Event]``. ``cmd`` is the parsed command
    model. **Check first, then change**: raise ``RuleError`` before mutating
    anything; once you mutate, you must not raise. ``state.now_ms == now_ms``.
``@timer_handler("dice_roll")``
    ``fn(state, timer, now_ms) -> list[Event]``. Called with ``state.now_ms`` and
    ``now_ms`` set to the timer's logical due time. Must not raise ``RuleError``.
``@on_new_game(order=100)``
    ``fn(state, now_ms) -> list[Event]``, run once by ``new_game`` (now_ms = 0).
``@after_step(order=100)``
    ``fn(state, now_ms) -> list[Event]``, run after every successful ``apply`` and
    after every ``advance`` that fired at least one timer (and at the end of
    ``new_game``). Hooks must depend only on the state (they may run more often
    than strictly needed) and must be idempotent when nothing changed.
``@connect(signal, order=100)``
    ``fn(state, now_ms, **kwargs) -> list[Event]``: synchronous cross-module
    callbacks; the owner calls ``emit(state, signal, now_ms, **kwargs)`` and adds
    the returned events to its own. See ``SIG_*`` below.

Hooks and signal listeners run in ``(order, registration order)``; registration
order is the fixed import order of :data:`RULE_MODULES`.

Host contract: call ``advance(state, now)`` before ``apply(state, seat, cmd, now)``
(timers due at the same ms fire before commands). ``apply`` raises ``EngineError``
if a timer due at or before ``now_ms`` has not been fired yet.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from engine.board.model import GeneratedBoard
from engine.commands import parse_command
from engine.errors import EngineError, RuleError
from engine.events import Event
from engine.rng import Rng
from engine.scheduler import Timer
from engine.settings.enums import BuildKind, Resource
from engine.settings.models import GameSettings
from engine.state import GameState, PlayerState, SeatInfo, empty_resources

__all__ = [
    "command_handler", "timer_handler", "on_new_game", "after_step", "connect", "emit",
    "new_game", "apply", "advance", "next_wakeup", "temporary_registry", "set_check_rejects",
    "derive_seeds", "RULE_MODULES",
    "TIMER_DICE_ROLL", "TIMER_SETTLER_ARRIVE", "TIMER_CONSTRUCTION_DONE",
    "SIG_SETTLER_DEPARTING", "SIG_BUILT",
]

CommandHandler = Callable[[GameState, int, Any, int], list[Event]]
TimerHandler = Callable[[GameState, Timer, int], list[Event]]
Hook = Callable[[GameState, int], list[Event]]
Listener = Callable[..., list[Event]]

# ---------------------------------------------------------------- shared names
TIMER_DICE_ROLL = "dice_roll"                   # payload {}            handler: rules.dice
TIMER_SETTLER_ARRIVE = "settler_arrive"         # payload {"settler"}   handler: rules.movement
TIMER_CONSTRUCTION_DONE = "construction_done"   # payload {"construction"} handler: rules.construction

SIG_SETTLER_DEPARTING = "settler_departing"
"""Emitted by movement when a settler starts walking off a vertex.
kwargs: ``settler: int, vertex: int`` (the vertex being left). Construction cancels
builds whose builder left (reason ``"builder_left"``)."""
SIG_BUILT = "built"
"""Emitted by construction right after a piece is placed on the board, before it
creates its ``built`` event (so listeners can update ``player.points`` first).
kwargs: ``seat: int, kind: BuildKind, target: int, setup: bool, construction: int``.
Listeners: setup (setup counters, starting resources, clock start, settler leaves),
victory (points)."""

RULE_MODULES: tuple[str, ...] = (
    "setup", "movement", "placement", "construction", "dice", "production", "robber", "trade", "victory",
)


class _Registry:
    def __init__(self) -> None:
        self.commands: dict[str, CommandHandler] = {}
        self.timers: dict[str, TimerHandler] = {}
        self.new_game: list[tuple[int, int, Hook]] = []
        self.after_step: list[tuple[int, int, Hook]] = []
        self.signals: dict[str, list[tuple[int, int, Listener]]] = {}
        self.counter = 0

    def copy(self) -> _Registry:
        r = _Registry()
        r.commands, r.timers = dict(self.commands), dict(self.timers)
        r.new_game, r.after_step = list(self.new_game), list(self.after_step)
        r.signals = {k: list(v) for k, v in self.signals.items()}
        r.counter = self.counter
        return r

    def ordered(self, entries: list[tuple[int, int, Any]]) -> list[Any]:
        return [fn for _, _, fn in sorted(entries, key=lambda e: (e[0], e[1]))]

    def next_index(self) -> int:
        self.counter += 1
        return self.counter


_REG = _Registry()
_CHECK_REJECTS = False


def command_handler(name: str) -> Callable[[CommandHandler], CommandHandler]:
    """Register the handler for command action ``name`` (one per action)."""
    def deco(fn: CommandHandler) -> CommandHandler:
        if name in _REG.commands:
            raise EngineError(f"duplicate command handler {name!r}")
        _REG.commands[name] = fn
        return fn
    return deco


def timer_handler(kind: str) -> Callable[[TimerHandler], TimerHandler]:
    """Register the handler for timer ``kind`` (one per kind)."""
    def deco(fn: TimerHandler) -> TimerHandler:
        if kind in _REG.timers:
            raise EngineError(f"duplicate timer handler {kind!r}")
        _REG.timers[kind] = fn
        return fn
    return deco


def on_new_game(order: int = 100) -> Callable[[Hook], Hook]:
    def deco(fn: Hook) -> Hook:
        _REG.new_game.append((order, _REG.next_index(), fn))
        return fn
    return deco


def after_step(order: int = 100) -> Callable[[Hook], Hook]:
    def deco(fn: Hook) -> Hook:
        _REG.after_step.append((order, _REG.next_index(), fn))
        return fn
    return deco


def connect(signal: str, order: int = 100) -> Callable[[Listener], Listener]:
    """Listen to ``signal``: ``fn(state, now_ms, **kwargs) -> list[Event]``."""
    def deco(fn: Listener) -> Listener:
        _REG.signals.setdefault(signal, []).append((order, _REG.next_index(), fn))
        return fn
    return deco


def emit(state: GameState, signal: str, now_ms: int, **kwargs: Any) -> list[Event]:
    """Call every listener of ``signal`` in order and return their events."""
    events: list[Event] = []
    for fn in _REG.ordered(_REG.signals.get(signal, [])):
        events.extend(fn(state, now_ms, **kwargs))
    return events


@contextmanager
def temporary_registry(empty: bool = False) -> Iterator[None]:
    """Tests: registrations made inside the block are removed afterwards.
    ``empty=True`` also hides every handler/hook registered by the rule modules."""
    global _REG
    saved = _REG
    _REG = _Registry() if empty else saved.copy()
    try:
        yield
    finally:
        _REG = saved


def set_check_rejects(enabled: bool) -> None:
    """Tests: when enabled, ``apply`` verifies that a handler raising ``RuleError``
    left the state unchanged (raises ``EngineError`` otherwise). Slow."""
    global _CHECK_REJECTS
    _CHECK_REJECTS = enabled


def _run_hooks(hooks: list[tuple[int, int, Hook]], state: GameState, now_ms: int) -> list[Event]:
    events: list[Event] = []
    for fn in _REG.ordered(hooks):
        events.extend(fn(state, now_ms))
    return events


# -------------------------------------------------------------------- new game
def derive_seeds(seed: int) -> tuple[int, int]:
    """``(board_seed, game_seed)`` derived deterministically from the game seed."""
    master = Rng(seed)
    return master.getrandbits(63), master.getrandbits(63)


def _check_seats(settings: GameSettings, seats: list[SeatInfo]) -> None:
    if [s.seat for s in seats] != list(range(len(seats))):
        raise EngineError("seats must be numbered 0..n-1 in order")
    if not settings.players.min <= len(seats) <= settings.players.max:
        raise RuleError("game.player_count", {"count": len(seats), "min": settings.players.min,
                                              "max": settings.players.max})


def _new_player(settings: GameSettings, info: SeatInfo) -> PlayerState:
    pieces = settings.pieces
    return PlayerState(
        seat=info.seat, info=info, hand=empty_resources(),
        pieces_left={BuildKind.ROAD: pieces.roads, BuildKind.SETTLEMENT: pieces.settlements,
                     BuildKind.CITY: pieces.cities, BuildKind.MEGACITY: pieces.megacities},
        setup_remaining={BuildKind.SETTLEMENT: settings.setup.settlements, BuildKind.ROAD: settings.setup.roads},
    )


def new_game(settings: GameSettings, seats: list[SeatInfo], seed: int,
             board: GeneratedBoard | None = None) -> tuple[GameState, list[Event]]:
    """Build the initial state (phase ``setup``, now 0) and run the ``on_new_game`` hooks.

    Board randomness uses ``settings.board.seed`` if set, else a seed derived from
    ``seed``; the game RNG always uses the derived game seed (independent of
    whether ``board`` is passed).
    """
    _check_seats(settings, seats)
    board_seed, game_seed = derive_seeds(seed)
    if board is None:
        from engine.board.generator import generate_board  # lazy: owned by WP3
        if settings.board.seed is not None:
            board_seed = settings.board.seed
        board = generate_board(settings, Rng(board_seed))
    bank = {r: settings.economy.bank.per_resource.get(r, 0) for r in Resource}
    state = GameState(
        settings=settings, board=board, rng=Rng(game_seed), seed=seed,
        players=[_new_player(settings, s) for s in seats], bank=bank,
        robber_hex=board.robber_start,
    )
    events = _run_hooks(_REG.new_game, state, 0)
    events += _run_hooks(_REG.after_step, state, 0)
    return state, events


# ----------------------------------------------------------------------- apply
def apply(state: GameState, seat: int, raw_or_cmd: Any, now_ms: int) -> list[Event]:
    """Apply one player command at game time ``now_ms``. Raises ``RuleError`` on reject
    (state unchanged). Codes: ``game.finished``, ``game.time_backwards``,
    ``command.unknown_seat``, ``command.invalid``, ``command.unsupported`` + handler codes."""
    if state.phase == "finished":
        raise RuleError("game.finished")
    if now_ms < state.now_ms:
        raise RuleError("game.time_backwards", {"now": now_ms, "state_now": state.now_ms})
    if not state.has_seat(seat):
        raise RuleError("command.unknown_seat", {"seat": seat})
    cmd = parse_command(raw_or_cmd)
    handler = _REG.commands.get(cmd.a)
    if handler is None:
        raise RuleError("command.unsupported", {"action": cmd.a})
    due = state.timers.next_due()
    if due is not None and due <= now_ms:
        raise EngineError(f"timers due at {due} not fired; call advance({now_ms}) before apply")
    before = _snapshot(state) if _CHECK_REJECTS else None
    old_now = state.now_ms
    state.now_ms = now_ms
    try:
        events = list(handler(state, seat, cmd, now_ms))
    except RuleError:
        state.now_ms = old_now
        if before is not None and _snapshot(state) != before:
            raise EngineError(f"handler {cmd.a!r} mutated state before raising RuleError") from None
        raise
    events += _run_hooks(_REG.after_step, state, now_ms)
    return events


def _snapshot(state: GameState) -> dict[str, Any]:
    from engine.codec import dump
    return dump(state)


# --------------------------------------------------------------------- advance
def advance(state: GameState, now_ms: int) -> list[Event]:
    """Fire every timer due at or before ``now_ms`` in ``(due_ms, seq)`` order, each at
    its logical due time (timers scheduled meanwhile are included), then set
    ``state.now_ms = now_ms`` and run the ``after_step`` hooks once if anything fired.
    Stops firing when the game finishes (``state.now_ms`` then stays at the end time)."""
    if now_ms < state.now_ms:
        raise EngineError(f"advance to {now_ms} < state.now_ms {state.now_ms}")
    if state.phase == "finished":
        return []
    events: list[Event] = []
    fired = False
    while state.phase != "finished" and (timer := state.timers.pop_next(now_ms)) is not None:
        handler = _REG.timers.get(timer.kind)
        if handler is None:
            raise EngineError(f"no handler for timer kind {timer.kind!r}")
        state.now_ms = max(state.now_ms, timer.due_ms)
        events.extend(handler(state, timer, state.now_ms))
        fired = True
    if state.phase != "finished":
        state.now_ms = now_ms
    if fired:
        events += _run_hooks(_REG.after_step, state, state.now_ms)
    return events


def next_wakeup(state: GameState) -> int | None:
    """Earliest pending timer due time, or None (also None once finished)."""
    if state.phase == "finished":
        return None
    return state.timers.next_due()


# Register the rule modules' handlers (their decorators run on import).
for _name in RULE_MODULES:
    importlib.import_module(f"engine.rules.{_name}")
