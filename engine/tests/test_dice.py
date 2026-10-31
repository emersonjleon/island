"""WP7 dice clock tests. Also hosts the WP7 test helpers (imported by the other WP7 tests).

The helpers build states with only the WP7 handlers registered, so these tests do
not depend on movement/setup/construction (WP5/WP6).
"""
from __future__ import annotations

import json
import math
import unittest
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from engine import codec, game
from engine.events import DiceRolled, Event, Produced, RobberMoved
from engine.rng import Rng
from engine.rules import dice, trade, victory
from engine.settings import parse_settings
from engine.settings.enums import BuildKind, Resource
from engine.state import Building, GameState
from engine.tests.fixtures import make_seats, standard_board

INTERVAL = 20000  # classic default roll_interval_ms (asserted below)


# ------------------------------------------------------------------- helpers
@contextmanager
def wp7_registry() -> Iterator[None]:
    """Only the WP7 handlers/hooks, registered as the rule modules register them."""
    with game.temporary_registry(empty=True):
        game.timer_handler(game.TIMER_DICE_ROLL)(dice.on_dice_roll)
        game.command_handler("bank_trade")(trade.on_bank_trade)
        game.connect(game.SIG_BUILT, order=victory.BUILT_ORDER)(victory.on_built)
        game.after_step(order=victory.AFTER_STEP_ORDER)(victory.check_victory)
        yield


class ScriptedRng(Rng):
    """An ``Rng`` whose ``dice`` returns scripted faces first, then real rolls."""

    def __init__(self, seed: int, rolls: Sequence[Sequence[int]] = ()) -> None:
        super().__init__(seed)
        self.rolls = [list(r) for r in rolls]

    def dice(self, n: int = 2, sides: int = 6) -> list[int]:
        if self.rolls:
            return self.rolls.pop(0)
        return super().dice(n, sides)


def make_state(n: int = 3, overrides: dict[str, Any] | None = None, *, stage: int | None = None,
               seed: int = 1, start_ms: int = 0, clock: bool = True, setup_done: bool = True,
               rolls: Sequence[Sequence[int]] | None = None, board: Any = None) -> GameState:
    """A game on the fixture board (call inside ``wp7_registry``). With ``clock`` the dice
    clock is started at ``start_ms`` (first roll one interval later), as setup would do."""
    settings = parse_settings(overrides or {}, implemented_stage=stage)
    state, _ = game.new_game(settings, make_seats(n), seed=seed, board=board or standard_board())
    for p in state.players:
        p.setup_done = setup_done
    if rolls is not None:
        state.rng = ScriptedRng(seed, rolls)
    if start_ms:
        game.advance(state, start_ms)
    if clock:
        state.clock_started = True
        state.phase = "running"
        dice.schedule_next_roll(state, start_ms + settings.clock.roll_interval_ms)
    return state


def place(state: GameState, seat: int, vertex: int, kind: BuildKind = BuildKind.SETTLEMENT) -> None:
    state.buildings[vertex] = Building(seat=seat, kind=kind)


def set_hand(state: GameState, seat: int, **cards: int) -> None:
    """Give ``seat`` exactly ``cards`` (taken from the bank, so totals are conserved)."""
    hand = state.players[seat].hand
    for r in Resource:
        state.bank[r] += hand[r]
        hand[r] = 0
    for name, n in cards.items():
        r = Resource(name)
        state.bank[r] -= n
        hand[r] = n


def totals(state: GameState) -> dict[Resource, int]:
    """Bank + hands + escrow per resource."""
    out = dict(state.bank)
    for p in state.players:
        for r in Resource:
            out[r] += p.hand[r]
    for c in state.constructions.values():
        for r, n in c.paid.items():
            out[r] += n
    return out


def of_kind(events: list[Event], cls: type) -> list[Any]:
    return [e for e in events if isinstance(e, cls)]


# --------------------------------------------------------------------- tests
class DiceRegistrationTest(unittest.TestCase):
    def test_registered_in_real_registry(self) -> None:
        reg = game._REG
        self.assertIs(reg.timers[game.TIMER_DICE_ROLL], dice.on_dice_roll)
        self.assertIs(reg.commands["bank_trade"], trade.on_bank_trade)
        self.assertIn(victory.on_built, [fn for _, _, fn in reg.signals[game.SIG_BUILT]])
        self.assertIn((victory.AFTER_STEP_ORDER, victory.check_victory),
                      [(o, fn) for o, _, fn in reg.after_step])
        self.assertEqual(parse_settings({}).clock.roll_interval_ms, INTERVAL)


class DiceClockTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = wp7_registry()
        self._reg.__enter__()

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)

    def test_first_roll_event(self) -> None:
        state = make_state(start_ms=1234)
        self.assertEqual(game.next_wakeup(state), 1234 + INTERVAL)
        self.assertEqual(game.advance(state, 1234 + INTERVAL - 1), [])
        events = game.advance(state, 1234 + INTERVAL)
        rolled = events[0]
        self.assertIsInstance(rolled, DiceRolled)
        self.assertEqual(rolled.at, 1234 + INTERVAL)
        self.assertEqual(rolled.sum, sum(rolled.dice))
        self.assertEqual(len(rolled.dice), 2)
        self.assertEqual(rolled.next_roll_at, 1234 + 2 * INTERVAL)
        self.assertEqual(state.last_roll, rolled.dice)
        self.assertEqual(state.dice_history, [rolled.sum])
        self.assertEqual(state.next_roll_at, 1234 + 2 * INTERVAL)
        self.assertEqual(state.timers.get(state.roll_timer_id).due_ms, 1234 + 2 * INTERVAL)  # type: ignore[union-attr]
        self.assertEqual(len(state.timers.pending(game.TIMER_DICE_ROLL)), 1)

    def test_no_drift_over_100_rolls_with_late_wakeups(self) -> None:
        state = make_state(start_ms=500)
        times: list[int] = []
        now = 500
        while len(state.dice_history) < 100:
            now += 7919  # wake up at irregular, late moments
            for e in game.advance(state, now):
                if isinstance(e, DiceRolled):
                    times.append(e.at)
                    self.assertEqual(e.next_roll_at, e.at + INTERVAL)
        self.assertEqual(times[:100], [500 + k * INTERVAL for k in range(1, 101)])
        self.assertEqual(len(state.timers.pending(game.TIMER_DICE_ROLL)), 1)

    def test_one_big_advance_fires_every_roll_at_its_time(self) -> None:
        state = make_state()
        events = game.advance(state, 100 * INTERVAL)
        times = [e.at for e in events if isinstance(e, DiceRolled)]
        self.assertEqual(times, [k * INTERVAL for k in range(1, 101)])
        self.assertEqual(state.next_roll_at, 101 * INTERVAL)
        self.assertEqual(state.now_ms, 100 * INTERVAL)

    def test_pause_after_seven(self) -> None:
        state = make_state(overrides={"clock": {"pause_after_seven_ms": 5000}}, stage=3,
                           rolls=[[3, 4], [2, 2], [6, 1], [1, 1]])
        events = game.advance(state, 10 * INTERVAL)
        rolled = of_kind(events, DiceRolled)
        self.assertEqual([e.sum for e in rolled[:4]], [7, 4, 7, 2])
        self.assertEqual([e.at for e in rolled[:5]],
                         [INTERVAL, 2 * INTERVAL + 5000, 3 * INTERVAL + 5000, 4 * INTERVAL + 10000,
                          5 * INTERVAL + 10000])

    def test_deterministic_for_a_seed(self) -> None:
        a, b, c = make_state(seed=5), make_state(seed=5), make_state(seed=6)
        for s in (a, b, c):
            game.advance(s, 50 * INTERVAL)
        self.assertEqual(a.dice_history, b.dice_history)
        self.assertEqual(codec.state_hash(a), codec.state_hash(b))
        self.assertNotEqual(a.dice_history, c.dice_history)

    def test_range_and_distribution(self) -> None:
        state = make_state(overrides={"robber": {"enabled": False}}, seed=11)
        n = 3600
        game.advance(state, n * INTERVAL)
        hist = state.dice_history
        self.assertEqual(len(hist), n)
        clock = state.settings.clock
        self.assertTrue(all(clock.min_roll <= s <= clock.max_roll for s in hist))
        for s in range(2, 13):
            expected = n * (6 - abs(s - 7)) // 36   # ways to roll s with 2d6 out of 36
            self.assertLess(abs(hist.count(s) - expected), 5 * math.isqrt(expected) + 10, f"sum {s}")

    def test_other_dice_shape(self) -> None:
        tokens = {"3": 3, "4": 2, "5": 2, "6": 2, "8": 2, "9": 2, "10": 2, "11": 2, "12": 1}
        state = make_state(overrides={"clock": {"dice_count": 3, "dice_sides": 4},
                                      "board": {"number_tokens": tokens}}, stage=3)
        self.assertEqual(state.settings.clock.robber_roll, 7)
        events = game.advance(state, 300 * INTERVAL)
        self.assertTrue(all(3 <= s <= 12 for s in state.dice_history))
        self.assertTrue(all(len(e.dice) == 3 and 1 <= min(e.dice) and max(e.dice) <= 4
                            for e in of_kind(events, DiceRolled)))
        self.assertEqual(min(state.dice_history), 3)
        self.assertEqual(max(state.dice_history), 12)

    def test_seven_produces_nothing_other_rolls_produce(self) -> None:
        state = make_state(rolls=[[3, 4], [4, 4]])
        seven = game.advance(state, INTERVAL)
        self.assertIsInstance(seven[0], DiceRolled)
        self.assertEqual(of_kind(seven, Produced), [])
        self.assertEqual(len(of_kind(seven, RobberMoved)), 1)
        eight = game.advance(state, 2 * INTERVAL)
        self.assertEqual([type(e) for e in eight], [DiceRolled, Produced])

    def test_seven_with_robber_disabled(self) -> None:
        state = make_state(overrides={"robber": {"enabled": False}}, rolls=[[3, 4]])
        events = game.advance(state, INTERVAL)
        self.assertEqual([type(e) for e in events], [DiceRolled])
        self.assertEqual(state.robber_hex, 9)
        self.assertEqual(state.next_roll_at, 2 * INTERVAL)

    def test_stale_roll_timer_ignored(self) -> None:
        state = make_state()
        state.timers.schedule(INTERVAL // 2, game.TIMER_DICE_ROLL, {})  # not the recorded roll timer
        self.assertEqual(game.advance(state, INTERVAL // 2), [])
        self.assertEqual(state.dice_history, [])
        game.advance(state, INTERVAL)
        self.assertEqual(len(state.dice_history), 1)

    def test_codec_round_trip_between_rolls(self) -> None:
        state = make_state(seed=3)
        place(state, 0, 31)                        # ore 8
        place(state, 1, 51, BuildKind.CITY)        # lumber 8
        place(state, 2, 16)                        # lumber 5, fish 4
        set_hand(state, 0, lumber=6, ore=4)
        game.advance(state, 7 * INTERVAL + 123)
        copy = codec.load(json.loads(json.dumps(codec.dump(state))))
        self.assertEqual(codec.state_hash(copy), codec.state_hash(state))
        ev_a = [e.to_dict() for e in game.advance(state, 60 * INTERVAL)]
        ev_b = [e.to_dict() for e in game.advance(copy, 60 * INTERVAL)]
        self.assertEqual(ev_a, ev_b)
        self.assertGreater(len(ev_a), 53)
        self.assertEqual(codec.state_hash(copy), codec.state_hash(state))


if __name__ == "__main__":
    unittest.main()
