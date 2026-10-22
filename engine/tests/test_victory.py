"""WP7 victory tests. Construction (WP6) is simulated by a test timer that emits
``SIG_BUILT`` and a ``Built`` event, as construction does."""
from __future__ import annotations

import json
import unittest

from engine import codec, game
from engine.errors import RuleError
from engine.events import Built, DiceRolled, Event, GameOver, Points
from engine.rules import victory
from engine.scheduler import Timer
from engine.settings.enums import BuildKind
from engine.state import GameState
from engine.tests.test_dice import (
    INTERVAL,
    make_state,
    of_kind,
    place,
    set_hand,
    wp7_registry,
)

TEST_BUILD = "test_build"
S, C, R = BuildKind.SETTLEMENT, BuildKind.CITY, BuildKind.ROAD


def fake_build(state: GameState, timer: Timer, now: int) -> list[Event]:
    seat, kind, target = timer.payload["seat"], BuildKind(timer.payload["kind"]), timer.payload["target"]
    if kind is not R:
        place(state, seat, target, kind)
    events = game.emit(state, game.SIG_BUILT, now, seat=seat, kind=kind, target=target, setup=False,
                       construction=timer.id)
    return events + [Built(at=now, seat=seat, kind=kind, target=target, points_after=state.players[seat].points)]


class VictoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = wp7_registry()
        self._reg.__enter__()
        game.timer_handler(TEST_BUILD)(fake_build)

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)

    def build_at(self, state: GameState, due: int, seat: int, kind: BuildKind, target: int) -> None:
        state.timers.schedule(due, TEST_BUILD, {"seat": seat, "kind": kind.value, "target": target})

    def test_points_per_building(self) -> None:
        s = make_state()
        ev = game.emit(s, game.SIG_BUILT, 5, seat=1, kind=S, target=31, setup=True, construction=1)
        self.assertEqual(ev, [Points(at=5, seat=1, points=1)])
        ev = game.emit(s, game.SIG_BUILT, 6, seat=1, kind=C, target=31, setup=False, construction=2)
        self.assertEqual(ev, [Points(at=6, seat=1, points=2)])
        self.assertEqual(game.emit(s, game.SIG_BUILT, 7, seat=1, kind=R, target=3, setup=False, construction=3), [])
        self.assertEqual([p.points for p in s.players], [0, 2, 0])

    def test_points_from_settings(self) -> None:
        s = make_state(overrides={"victory": {"building_points": {"settlement": 2, "city": 5}}})
        game.emit(s, game.SIG_BUILT, 0, seat=0, kind=S, target=31, setup=False, construction=1)
        game.emit(s, game.SIG_BUILT, 0, seat=0, kind=C, target=31, setup=False, construction=2)
        self.assertEqual(s.players[0].points, 5)

    def test_event_order_and_points_after(self) -> None:
        s = make_state()
        self.build_at(s, 100, 2, S, 31)
        events = game.advance(s, 100)
        self.assertEqual(events, [Points(at=100, seat=2, points=1),
                                  Built(at=100, seat=2, kind=S, target=31, points_after=1)])
        self.assertEqual(s.phase, "running")

    def test_game_over_at_target(self) -> None:
        s = make_state()
        target = s.settings.victory.target
        s.players[1].points = target - 1
        s.players[2].points = target - 1
        self.build_at(s, INTERVAL + 50, 1, C, 31)          # +1 -> target
        self.build_at(s, INTERVAL + 60, 2, S, 51)          # would also reach it, but the game is over
        events = game.advance(s, 5 * INTERVAL)
        self.assertIsInstance(events[0], DiceRolled)
        self.assertEqual([type(e) for e in events[-3:]], [Points, Built, GameOver])
        self.assertEqual(len(of_kind(events, GameOver)), 1)
        over = events[-1]
        self.assertEqual(over, GameOver(at=INTERVAL + 50, winner=1,
                                        points={0: 0, 1: target, 2: target - 1}))
        self.assertEqual(s.phase, "finished")
        self.assertEqual(s.winner, 1)
        self.assertEqual(s.finished_at, INTERVAL + 50)
        self.assertEqual(s.now_ms, INTERVAL + 50)
        self.assertEqual(len(s.dice_history), 1)             # no roll after the win
        self.assertIsNone(s.roll_timer_id)
        self.assertIsNone(s.next_roll_at)
        self.assertEqual(s.timers.pending(game.TIMER_DICE_ROLL), [])
        self.assertIsNone(game.next_wakeup(s))
        self.assertEqual(game.advance(s, 50 * INTERVAL), [])
        self.assertEqual(len(s.dice_history), 1)
        self.assertEqual(s.players[2].points, target - 1)
        with self.assertRaises(RuleError) as cm:
            game.apply(s, 0, {"a": "bank_trade", "give": {"lumber": 4}, "get": {"ore": 1}}, 50 * INTERVAL)
        self.assertEqual(cm.exception.code, "game.finished")

    def test_win_in_same_ms_as_roll(self) -> None:
        s = make_state()
        s.players[0].points = s.settings.victory.target - 1
        self.build_at(s, INTERVAL, 0, S, 31)               # scheduled after the roll timer: roll fires first
        events = game.advance(s, INTERVAL)
        self.assertIsInstance(events[0], DiceRolled)
        self.assertIsInstance(events[-1], GameOver)
        self.assertEqual(s.winner, 0)

    def test_after_step_check_and_tie_rule(self) -> None:
        s = make_state()
        target = s.settings.victory.target
        s.players[0].points = target
        s.players[1].points = target + 1
        s.players[2].points = target + 1
        events = victory.check_victory(s, 777)
        self.assertEqual(events, [GameOver(at=777, winner=1, points={0: target, 1: target + 1, 2: target + 1})])
        self.assertEqual((s.phase, s.winner, s.finished_at), ("finished", 1, 777))
        self.assertEqual(victory.check_victory(s, 778), [])    # announced once

    def test_check_is_noop_below_target(self) -> None:
        s = make_state()
        s.players[0].points = s.settings.victory.target - 1
        self.assertEqual(victory.check_victory(s, 0), [])
        self.assertEqual(s.phase, "running")
        self.assertEqual(s.ext, {})

    def test_target_from_settings(self) -> None:
        s = make_state(overrides={"victory": {"target": 5}})
        s.players[2].points = 4
        self.build_at(s, 10, 2, S, 31)
        events = game.advance(s, 10)
        self.assertEqual(events[-1].winner, 2)  # type: ignore[attr-defined]

    def test_finished_state_round_trips(self) -> None:
        s = make_state()
        set_hand(s, 0, ore=3)
        s.players[0].points = s.settings.victory.target - 1
        self.build_at(s, 3 * INTERVAL + 1, 0, S, 31)
        game.advance(s, 4 * INTERVAL)
        copy = codec.load(json.loads(json.dumps(codec.dump(s))))
        self.assertEqual(codec.state_hash(copy), codec.state_hash(s))
        self.assertEqual(copy.phase, "finished")
        self.assertEqual(victory.check_victory(copy, copy.now_ms), [])
        self.assertEqual(game.advance(copy, 100 * INTERVAL), [])


if __name__ == "__main__":
    unittest.main()
