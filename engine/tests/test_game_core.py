import importlib
import unittest

from engine import game
from engine.commands import Build, MoveSettler
from engine.errors import EngineError, RuleError
from engine.events import Built, ClockStarted, Points, SetupComplete
from engine.settings.enums import BuildKind, Resource
from engine.state import GameState
from engine.tests.fixtures import make_seats, make_settings, standard_board


def fresh(n: int = 3, settings_overrides: dict | None = None) -> GameState:
    state, _ = game.new_game(make_settings(settings_overrides), make_seats(n), seed=1, board=standard_board())
    return state


class NewGameTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = game.temporary_registry(empty=True)
        self._reg.__enter__()

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)

    def test_bare_state(self) -> None:
        settings = make_settings({"economy": {"bank": {"per_resource": 17}}, "pieces": {"roads": 12},
                                  "setup": {"settlements": 2, "roads": 1}})
        state, events = game.new_game(settings, make_seats(4), seed=3, board=standard_board())
        self.assertEqual(events, [])
        self.assertEqual(state.phase, "setup")
        self.assertEqual(state.now_ms, 0)
        self.assertEqual(state.bank, {r: 17 for r in Resource})
        self.assertEqual(state.robber_hex, 9)
        self.assertEqual(len(state.players), 4)
        for i, p in enumerate(state.players):
            self.assertEqual(p.seat, i)
            self.assertEqual(p.hand, {r: 0 for r in Resource})
            self.assertEqual(p.pieces_left, {BuildKind.ROAD: 12, BuildKind.SETTLEMENT: 5, BuildKind.CITY: 4,
                                             BuildKind.MEGACITY: 4})
            self.assertEqual(p.setup_remaining, {BuildKind.SETTLEMENT: 2, BuildKind.ROAD: 1})
            self.assertFalse(p.setup_done)
        self.assertEqual(len(state.timers), 0)
        self.assertEqual(state.next_id("settler"), 1)
        self.assertEqual(state.next_id("settler"), 2)
        self.assertEqual(state.next_id("construction"), 1)

    def test_game_rng_from_derived_seed(self) -> None:
        a = fresh()
        b = fresh()
        self.assertEqual(a.rng, b.rng)
        _, game_seed = game.derive_seeds(1)
        from engine.rng import Rng
        self.assertEqual(a.rng, Rng(game_seed))
        self.assertNotEqual(*game.derive_seeds(1))

    def test_seat_validation(self) -> None:
        seats = make_seats(3)
        seats[1].seat = 5
        with self.assertRaises(EngineError):
            game.new_game(make_settings(), seats, 1, board=standard_board())
        with self.assertRaises(RuleError) as cm:
            game.new_game(make_settings(), make_seats(5), 1, board=standard_board())
        self.assertEqual(cm.exception.code, "game.player_count")

    def test_hooks_order_and_events(self) -> None:
        calls: list[str] = []

        @game.on_new_game(order=200)
        def late(state: GameState, now: int) -> list:
            calls.append("late")
            return [SetupComplete(at=now, seat=1)]

        @game.on_new_game(order=50)
        def early(state: GameState, now: int) -> list:
            calls.append("early")
            return [SetupComplete(at=now, seat=0)]

        @game.after_step()
        def step(state: GameState, now: int) -> list:
            calls.append("after")
            return []

        _, events = game.new_game(make_settings(), make_seats(2), 1, board=standard_board())
        self.assertEqual(calls, ["early", "late", "after"])
        self.assertEqual([e.seat for e in events], [0, 1])  # type: ignore[attr-defined]


class ApplyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = game.temporary_registry(empty=True)
        self._reg.__enter__()
        self.after_calls: list[int] = []

        @game.after_step()
        def count(state: GameState, now: int) -> list:
            self.after_calls.append(now)
            return []

        self.state = fresh()
        self.after_calls.clear()

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)
        game.set_check_rejects(False)

    def assertRule(self, code: str, *args: object) -> RuleError:
        with self.assertRaises(RuleError) as cm:
            game.apply(*args)  # type: ignore[arg-type]
        self.assertEqual(cm.exception.code, code)
        return cm.exception

    def test_unsupported(self) -> None:
        err = self.assertRule("command.unsupported", self.state, 0, {"a": "build", "kind": "road", "edge": 1}, 10)
        self.assertEqual(err.params, {"action": "build"})
        self.assertEqual(self.state.now_ms, 0)
        self.assertEqual(self.after_calls, [])

    def test_invalid_and_unknown_seat(self) -> None:
        self.assertRule("command.invalid", self.state, 0, {"a": "nope"}, 10)
        self.assertRule("command.unknown_seat", self.state, 3, MoveSettler(settler=1, to_vertex=2), 10)
        self.assertRule("command.unknown_seat", self.state, -1, MoveSettler(settler=1, to_vertex=2), 10)

    def test_dispatch(self) -> None:
        seen = []

        @game.command_handler("build")
        def build(state: GameState, seat: int, cmd: Build, now: int) -> list:
            seen.append((seat, cmd, now, state.now_ms))
            return [Built(at=now, seat=seat, kind=cmd.kind, target=cmd.target, points_after=1)]

        events = game.apply(self.state, 2, {"t": "intent", "cid": "c1", "a": "build", "kind": "settlement",
                                            "vertex": 4}, 500)
        self.assertEqual(seen, [(2, Build(kind=BuildKind.SETTLEMENT, vertex=4), 500, 500)])
        self.assertEqual([e.k for e in events], ["built"])
        self.assertEqual(self.state.now_ms, 500)
        self.assertEqual(self.after_calls, [500])
        game.apply(self.state, 2, Build(kind=BuildKind.ROAD, edge=4), 500)   # same ms is fine
        self.assertRule("game.time_backwards", self.state, 0, Build(kind=BuildKind.ROAD, edge=4), 499)

    def test_reject_restores_time(self) -> None:
        @game.command_handler("cancel_build")
        def cancel(state: GameState, seat: int, cmd: object, now: int) -> list:
            raise RuleError("build.unknown_construction", {"construction": 1})

        self.assertRule("build.unknown_construction", self.state, 0, {"a": "cancel_build", "construction": 1}, 900)
        self.assertEqual(self.state.now_ms, 0)
        self.assertEqual(self.after_calls, [])

    def test_check_rejects_detects_mutation(self) -> None:
        @game.command_handler("cancel_build")
        def bad(state: GameState, seat: int, cmd: object, now: int) -> list:
            state.bank[Resource.ORE] -= 1
            raise RuleError("x.y")

        game.set_check_rejects(True)
        with self.assertRaises(EngineError):
            game.apply(self.state, 0, {"a": "cancel_build", "construction": 1}, 5)

    def test_finished(self) -> None:
        self.state.phase = "finished"
        self.assertRule("game.finished", self.state, 0, MoveSettler(settler=1, to_vertex=2), 10)

    def test_pending_timer_requires_advance(self) -> None:
        @game.command_handler("move_settler")
        def move(state: GameState, seat: int, cmd: object, now: int) -> list:
            return []

        @game.timer_handler("tick")
        def tick(state: GameState, timer: object, now: int) -> list:
            return []

        self.state.timers.schedule(100, "tick")
        game.apply(self.state, 0, MoveSettler(settler=1, to_vertex=2), 99)
        with self.assertRaises(EngineError):
            game.apply(self.state, 0, MoveSettler(settler=1, to_vertex=2), 100)
        game.advance(self.state, 100)
        game.apply(self.state, 0, MoveSettler(settler=1, to_vertex=2), 100)

    def test_duplicate_registration(self) -> None:
        game.command_handler("build")(lambda *a: [])
        with self.assertRaises(EngineError):
            game.command_handler("build")(lambda *a: [])
        game.timer_handler("k")(lambda *a: [])
        with self.assertRaises(EngineError):
            game.timer_handler("k")(lambda *a: [])


class AdvanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = game.temporary_registry(empty=True)
        self._reg.__enter__()
        self.fired: list[tuple[str, int, int, int]] = []
        self.after_calls: list[int] = []

        @game.after_step()
        def count(state: GameState, now: int) -> list:
            self.after_calls.append(now)
            return []

        @game.timer_handler("a")
        def a(state: GameState, timer, now: int) -> list:  # type: ignore[no-untyped-def]
            self.fired.append(("a", timer.id, now, state.now_ms))
            chain = timer.payload.get("chain")
            if chain:
                state.timers.schedule(now + chain[0], "a", {"chain": chain[1:]})
            return [Points(at=now, seat=0, points=timer.id)]

        self.state = fresh()
        self.after_calls.clear()

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)

    def test_fires_at_logical_times_in_order(self) -> None:
        t = self.state.timers
        x = t.schedule(300, "a")
        y = t.schedule(100, "a")
        z = t.schedule(300, "a")
        late = t.schedule(1001, "a")
        events = game.advance(self.state, 1000)
        self.assertEqual([(f[1], f[2], f[3]) for f in self.fired], [(y, 100, 100), (x, 300, 300), (z, 300, 300)])
        self.assertEqual([e.at for e in events], [100, 300, 300])
        self.assertEqual(self.state.now_ms, 1000)
        self.assertEqual(self.after_calls, [1000])
        self.assertEqual(game.next_wakeup(self.state), 1001)
        self.assertIsNotNone(t.get(late))

    def test_chained_timers(self) -> None:
        t = self.state.timers
        t.schedule(100, "a", {"chain": [50, 50, 900]})   # 100 -> 150 -> 200 -> 1100
        t.schedule(180, "a")
        game.advance(self.state, 1000)
        self.assertEqual([f[2] for f in self.fired], [100, 150, 180, 200])
        self.assertEqual(game.next_wakeup(self.state), 1100)
        self.assertEqual(self.after_calls, [1000])

    def test_zero_delay_chain_same_ms(self) -> None:
        self.state.timers.schedule(100, "a", {"chain": [0, 0]})
        self.state.timers.schedule(100, "a")
        game.advance(self.state, 100)
        self.assertEqual([f[2] for f in self.fired], [100, 100, 100, 100])
        self.assertEqual([f[1] for f in self.fired], [1, 2, 3, 4])

    def test_noop_advance_runs_no_hooks(self) -> None:
        self.assertEqual(game.advance(self.state, 50), [])
        self.assertEqual(self.state.now_ms, 50)
        self.assertEqual(self.after_calls, [])
        self.assertIsNone(game.next_wakeup(self.state))

    def test_backwards_and_unknown_kind(self) -> None:
        game.advance(self.state, 50)
        with self.assertRaises(EngineError):
            game.advance(self.state, 49)
        self.state.timers.schedule(60, "nobody")
        with self.assertRaises(EngineError):
            game.advance(self.state, 60)

    def test_cancelled_timers_skipped(self) -> None:
        tid = self.state.timers.schedule(10, "a")
        self.state.timers.schedule(20, "a")
        self.state.timers.cancel(tid)
        game.advance(self.state, 100)
        self.assertEqual([f[2] for f in self.fired], [20])

    def test_stops_when_finished(self) -> None:
        @game.timer_handler("end")
        def end(state: GameState, timer, now: int) -> list:  # type: ignore[no-untyped-def]
            state.phase = "finished"
            state.finished_at = now
            return []

        self.state.timers.schedule(10, "a")
        self.state.timers.schedule(20, "end")
        self.state.timers.schedule(30, "a")
        game.advance(self.state, 100)
        self.assertEqual([f[2] for f in self.fired], [10])
        self.assertEqual(self.state.now_ms, 20)
        self.assertIsNone(game.next_wakeup(self.state))
        self.assertEqual(game.advance(self.state, 200), [])


class SignalsAndRegistryTest(unittest.TestCase):
    def test_signals_in_order(self) -> None:
        with game.temporary_registry(empty=True):
            state = fresh()
            calls = []

            @game.connect("sig", order=20)
            def second(state: GameState, now: int, **kw: object) -> list:
                calls.append(("second", kw))
                return [ClockStarted(at=now, next_roll_at=now + 1)]

            @game.connect("sig", order=10)
            def first(state: GameState, now: int, **kw: object) -> list:
                calls.append(("first", kw))
                return []

            events = game.emit(state, "sig", 7, settler=3)
            self.assertEqual(calls, [("first", {"settler": 3}), ("second", {"settler": 3})])
            self.assertEqual([e.at for e in events], [7])
            self.assertEqual(game.emit(state, "other", 7), [])

    def test_temporary_registry_restores(self) -> None:
        before = dict(game._REG.commands)
        with game.temporary_registry():
            game.command_handler("__test__")(lambda *a: [])
            self.assertIn("__test__", game._REG.commands)
        self.assertEqual(game._REG.commands, before)

    def test_rule_modules_import(self) -> None:
        for name in game.RULE_MODULES:
            mod = importlib.import_module(f"engine.rules.{name}")
            self.assertTrue(mod.__doc__)


if __name__ == "__main__":
    unittest.main()
