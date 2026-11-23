"""WP26 ages: advancing, cancelling, reaching, and what an age changes."""
from __future__ import annotations

import unittest
from typing import Any

from engine import game
from engine.errors import RuleError
from engine.events import AgeAdvanceCancelled, AgeAdvanceStarted, AgeReached, Buildable, Hand, Points
from engine.rules import age_state, ages, construction, placement, production, robber
from engine.settings.enums import BuildKind, Resource
from engine.sim.invariants import resource_totals
from engine.state import GameState
from engine.tests.test_dice import make_state, place, set_hand

ON = {"ages": {"enabled": True}}
AGE2 = dict(fish=2, grain=1, wool=1, brick=1)
AGE3 = dict(fish=2, grain=2, ore=2)
FISHING_HEX = 19            # fixture board: a fishing ground with token 4
FISHING_VERTEX = 16         # a corner of it


def new_state(overrides: dict[str, Any] | None = None, n: int = 3) -> GameState:
    merged: dict[str, Any] = {"ages": {"enabled": True}}
    for key, value in (overrides or {}).items():
        merged[key] = {**merged.get(key, {}), **value}
    return make_state(n=n, overrides=merged, stage=3, clock=False)


def code(state: GameState, seat: int, raw: dict[str, Any], now: int = 0) -> tuple[str, dict[str, Any]]:
    try:
        game.apply(state, seat, raw, now)
    except RuleError as exc:
        return exc.code, dict(exc.params)
    raise AssertionError("no reject")


def kinds(events: list[Any]) -> list[type]:
    """Event types, leaving out the ``Buildable`` hints added after every step."""
    return [type(e) for e in events if not isinstance(e, Buildable)]


def set_age(state: GameState, seat: int, age: int) -> None:
    age_state.ext(state)["age"][str(seat)] = age


class AdvanceTest(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        s = make_state(stage=3, clock=False)
        self.assertEqual(code(s, 0, {"a": "advance_age"})[0], "age.disabled")
        self.assertEqual(age_state.age_of(s, 0), 1)

    def test_requirements(self) -> None:
        s = new_state()
        s.players[0].setup_done = False
        self.assertEqual(code(s, 0, {"a": "advance_age"})[0], "age.setup_not_done")
        s.players[0].setup_done = True
        self.assertEqual(code(s, 0, {"a": "advance_age"})[0], "age.cannot_afford")
        s1 = new_state({"ages": {"age2": {"requires": {"cities": 1}}}})
        self.assertEqual(code(s1, 0, {"a": "advance_age"}), ("age.need_cities", {"need": 1, "have": 0}))
        place(s1, 0, 5, BuildKind.CITY)
        self.assertEqual(code(s1, 0, {"a": "advance_age"})[0], "age.cannot_afford")
        s2 = new_state({"ages": {"enabled": True, "age2": {"requires": {"cities": 0, "points": 3}}}})
        self.assertEqual(code(s2, 0, {"a": "advance_age"}), ("age.need_points", {"need": 3, "have": 0}))

    def test_advance_pays_waits_and_reaches_age_two(self) -> None:
        s = new_state()
        place(s, 0, 5, BuildKind.CITY)
        s.players[0].points = 2
        set_hand(s, 0, **AGE2, lumber=1)
        before = resource_totals(s)
        events = game.apply(s, 0, {"a": "advance_age"}, 100)
        self.assertEqual(kinds(events), [AgeAdvanceStarted, Hand])
        self.assertEqual((events[0].age, events[0].t0, events[0].t1), (2, 100, 30100))
        self.assertEqual(s.players[0].hand_count, 1)
        self.assertEqual(resource_totals(s), before)
        self.assertEqual(code(s, 0, {"a": "advance_age"}, 200)[0], "age.in_progress")
        self.assertEqual(kinds(game.advance(s, 30099)), [])
        events = game.advance(s, 30100)
        self.assertEqual(kinds(events), [AgeReached, Points])
        self.assertEqual(age_state.age_of(s, 0), 2)
        self.assertEqual(s.players[0].points, 3)
        self.assertIsNone(age_state.advancing(s, 0))
        self.assertEqual(resource_totals(s), before)

    def test_age_three_needs_two_cities_and_age_three_is_the_last(self) -> None:
        s = new_state()
        set_age(s, 0, 2)
        place(s, 0, 5, BuildKind.CITY)
        set_hand(s, 0, **AGE3)
        self.assertEqual(code(s, 0, {"a": "advance_age"}), ("age.need_cities", {"need": 2, "have": 1}))
        place(s, 0, 30, BuildKind.MEGACITY)            # megacities count as cities
        game.apply(s, 0, {"a": "advance_age"}, 0)
        game.advance(s, 45000)
        self.assertEqual(age_state.age_of(s, 0), 3)
        self.assertEqual(s.players[0].points, 2)
        self.assertEqual(code(s, 0, {"a": "advance_age"}, 45000), ("age.max", {"age": 3}))

    def test_zero_time_reaches_at_once(self) -> None:
        s = new_state({"ages": {"age2": {"time_ms": 0, "requires": {"cities": 0}}}})
        set_hand(s, 0, **AGE2)
        events = game.apply(s, 0, {"a": "advance_age"}, 0)
        self.assertEqual(kinds(events), [AgeAdvanceStarted, Hand, AgeReached, Points])

    def test_reaching_the_target_ends_the_game(self) -> None:
        s = new_state({"ages": {"age2": {"requires": {"cities": 0}}}})
        s.players[1].points = s.settings.victory.target - 1
        set_hand(s, 1, **AGE2)
        game.apply(s, 1, {"a": "advance_age"}, 0)
        game.advance(s, 30000)
        self.assertEqual((s.phase, s.winner), ("finished", 1))


class CancelTest(unittest.TestCase):
    def test_cancel_refunds_like_a_construction(self) -> None:
        s = new_state({"ages": {"age2": {"requires": {"cities": 0}}}, "build": {"refund_pct": 50}})
        set_hand(s, 0, **AGE2)
        before = resource_totals(s)
        bank_fish = s.bank[Resource.FISH]
        game.apply(s, 0, {"a": "advance_age"}, 0)
        events = game.apply(s, 0, {"a": "cancel_age"}, 10)
        self.assertEqual(kinds(events), [AgeAdvanceCancelled, Hand])
        self.assertEqual(events[0].refund, {Resource.FISH: 1})
        self.assertEqual(s.players[0].hand[Resource.FISH], 1)
        self.assertEqual(s.bank[Resource.FISH], bank_fish + 1)
        self.assertEqual(resource_totals(s), before)
        self.assertEqual(kinds(game.advance(s, 30000)), [])   # the timer is gone
        self.assertEqual(age_state.age_of(s, 0), 1)
        self.assertEqual(code(s, 0, {"a": "cancel_age"}, 30000)[0], "age.not_advancing")

    def test_resigning_cancels_the_research(self) -> None:
        s = new_state({"ages": {"age2": {"requires": {"cities": 0}}}})
        set_hand(s, 0, **AGE2)
        before = resource_totals(s)
        game.apply(s, 0, {"a": "advance_age"}, 0)
        events = game.apply(s, 0, {"a": "resign"}, 5)
        self.assertIn(AgeAdvanceCancelled, kinds(events))
        self.assertIsNone(age_state.advancing(s, 0))
        self.assertEqual(resource_totals(s), before)


class EffectsTest(unittest.TestCase):
    def test_megacity_locked_until_age_three(self) -> None:
        s = new_state()
        self.assertEqual(placement.mode_error(s, 0, BuildKind.MEGACITY)[1].code, "age.locked")
        self.assertIsNone(placement.mode_error(s, 0, BuildKind.CITY)[1])
        set_age(s, 0, 3)
        self.assertIsNone(placement.mode_error(s, 0, BuildKind.MEGACITY)[1])
        off = make_state(stage=3, clock=False)
        self.assertIsNone(placement.mode_error(off, 0, BuildKind.MEGACITY)[1])

    def test_unlock_map_can_lock_cities(self) -> None:
        s = new_state({"ages": {"unlock": {"city": 2}}})
        err = placement.mode_error(s, 0, BuildKind.CITY)[1]
        self.assertEqual((err.code, err.params), ("age.locked", {"kind": "city", "age": 2}))

    def test_safe_hand_size_grows_with_the_ages(self) -> None:
        s = new_state()
        for seat in range(3):
            set_hand(s, seat, lumber=9)
        set_age(s, 1, 2)                                # limit 8: still robbed with 9
        set_age(s, 2, 3)                                # limit 9: safe
        self.assertEqual(robber.targets(s, s.robber_hex), [0, 1])

    def test_build_times_shrink(self) -> None:
        s = new_state()
        self.assertEqual(construction.build_time(s, BuildKind.CITY, False, 0), 10000)
        set_age(s, 0, 2)
        self.assertEqual(construction.build_time(s, BuildKind.CITY, False, 0), 8500)
        set_age(s, 0, 3)
        self.assertEqual(construction.build_time(s, BuildKind.CITY, False, 0), 7000)

    def test_extra_fish_on_fishing_grounds(self) -> None:
        s = new_state()
        place(s, 0, FISHING_VERTEX)
        roll = s.board.token[FISHING_HEX]
        self.assertEqual(production.owed_by_resource(s, roll)[0][Resource.FISH][0], 1)
        set_age(s, 0, 2)
        self.assertEqual(production.owed_by_resource(s, roll)[0][Resource.FISH][0], 2)
        set_age(s, 0, 3)
        self.assertEqual(production.owed_by_resource(s, roll)[0][Resource.FISH][0], 3)

    def test_ages_are_public_in_the_view(self) -> None:
        s = new_state({"ages": {"age2": {"requires": {"cities": 0}}}})
        set_hand(s, 0, **AGE2)
        game.apply(s, 0, {"a": "advance_age"}, 0)
        view = ages.state_view(s, 2)
        self.assertEqual(view["players"]["0"]["advancing"], {"age": 2, "t0": 0, "t1": 30000})
        self.assertEqual(view["players"]["1"], {"age": 1, "advancing": None, "reached": {}})
        self.assertEqual(ages.state_view(make_state(stage=3, clock=False), 0), {})


if __name__ == "__main__":
    unittest.main()


class SimulationTest(unittest.TestCase):
    def test_bot_games_with_ages_on_finish_and_keep_the_invariants(self) -> None:
        from engine.settings import load_preset
        from engine.sim.bots import make_bot
        from engine.sim.runner import Simulation
        from engine.tests.fixtures import make_seats
        for seed in (1, 2):
            settings = load_preset("classic", {"ages": {"enabled": True}}, implemented_stage=3)
            sim = Simulation(settings, make_seats(4), seed, [make_bot("greedy", i, seed * 10 + i) for i in range(4)])
            sim.run(max_ms=4 * 3600 * 1000)
            self.assertTrue(sim.state.finished, seed)
