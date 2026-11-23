"""WP26 ages: advancing, cancelling, reaching, and what an age changes."""
from __future__ import annotations

import unittest
from typing import Any

from engine import game
from engine.errors import RuleError
from engine.events import AgeAdvanceCancelled, AgeAdvanceStarted, AgeReached, Buildable, Hand, LargestPopulation, Points
from engine.rules import age_state, ages, construction, largest_population, placement, production, robber, settlers
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
        self.assertEqual(code(s, 0, {"a": "advance_age"}), ("age.need_cities", {"need": 1, "have": 0}))
        place(s, 0, 5, BuildKind.CITY)
        self.assertEqual(code(s, 0, {"a": "advance_age"})[0], "age.cannot_afford")
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
        self.assertEqual(s.players[0].points, 3)
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


def place_built(state: GameState, seat: int, vertex: int, kind: BuildKind) -> list[Any]:
    """Put a building down and run the "built" listeners (points, awards)."""
    place(state, seat, vertex, kind)
    return game.emit(state, game.SIG_BUILT, 0, seat=seat, kind=kind, target=vertex, setup=False, construction=0)


class LargestPopulationTest(unittest.TestCase):
    def test_award_moves_to_a_strictly_larger_population(self) -> None:
        s = new_state({"ages": {"largest_population": {"min": 3}}})
        place_built(s, 0, 5, BuildKind.CITY)                  # population 2
        self.assertIsNone(largest_population.holder(s))
        before = s.players[0].points
        events = place_built(s, 0, 30, BuildKind.SETTLEMENT)  # 3
        self.assertEqual(largest_population.holder(s), 0)
        self.assertEqual(s.players[0].points, before + 1 + 2)
        self.assertIn(LargestPopulation, kinds(events))
        place_built(s, 1, 40, BuildKind.CITY)
        place_built(s, 1, 45, BuildKind.SETTLEMENT)           # 3: a tie keeps the holder
        self.assertEqual(largest_population.holder(s), 0)
        p0, p1 = s.players[0].points, s.players[1].points
        place_built(s, 1, 49, BuildKind.SETTLEMENT)           # 4
        self.assertEqual(largest_population.holder(s), 1)
        self.assertEqual((s.players[0].points, s.players[1].points), (p0 - 2, p1 + 1 + 2))
        self.assertEqual(ages.state_view(s, 2)["largest_population"]["holder"], 1)

    def test_only_with_ages(self) -> None:
        s = make_state(stage=3, clock=False)
        for v in (5, 30, 45):
            place_built(s, 0, v, BuildKind.CITY)
        self.assertIsNone(largest_population.holder(s))


class AgeGatesTest(unittest.TestCase):
    def test_fish_ransom_from_age_two(self) -> None:
        s = new_state({"robber": {"fish_ransom": 2}})
        set_hand(s, 0, lumber=6, fish=4)
        lost = robber._fish_ransom(s, 0)
        self.assertIsNone(lost)                         # age I: robbed as usual
        set_age(s, 0, 2)
        self.assertEqual(robber._fish_ransom(s, 0), {Resource.FISH: 2})

    def test_settlers_gather_from_age_two_and_guard_from_age_three(self) -> None:
        from engine.tests.test_settlers import land_vertex_with_resources, only_settler, staying
        s = make_state(n=3, overrides=staying({"ages": {"enabled": True},
                                               "settlers": {"gather": True, "block_robber": True}}), stage=3)
        v = land_vertex_with_resources(s)
        only_settler(s, 0, v)
        self.assertEqual(settlers.gather(s, 3, 0), [])
        self.assertEqual(settlers.blocked_hexes(s), frozenset())
        set_age(s, 0, 2)
        self.assertTrue(settlers.gather(s, 3, 0))
        self.assertEqual(settlers.blocked_hexes(s), frozenset())
        set_age(s, 0, 3)
        self.assertTrue(settlers.blocked_hexes(s))


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

    def test_more_production_in_later_ages(self) -> None:
        s = new_state({"ages": {"age2": {"bonus": {"extra_per_city": 1}}}})
        h = next(h for h in range(len(s.board.token)) if s.board.hex_resource(h) is not None
                 and h not in s.board.fishing and h != s.robber_hex and s.board.token[h] is not None)
        v = s.board.board.hex_vertices[h][0]
        place(s, 0, v, BuildKind.CITY)
        roll, res = s.board.token[h], s.board.hex_resource(h)
        base = production.owed_by_resource(s, roll)[0][res][0]
        set_age(s, 0, 2)                                # cities + 1
        self.assertEqual(production.owed_by_resource(s, roll)[0][res][0], base + 1)
        plain = new_state()                             # off by default
        place(plain, 0, v, BuildKind.CITY)
        set_age(plain, 0, 3)
        self.assertEqual(production.owed_by_resource(plain, roll)[0][res][0], base)
        off = make_state(stage=3, clock=False)
        place(off, 0, v, BuildKind.CITY)
        self.assertEqual(production.owed_by_resource(off, roll)[0][res][0], base)

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
