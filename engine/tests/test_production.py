"""WP7 production tests (fixture board: hex 4 = ore/8, hex 11 = lumber/8, hex 10 = ore/4,
fishing ground 19 = fish/4, desert 9 holds the robber)."""
from __future__ import annotations

import unittest

from engine import game
from engine.events import DiceRolled, Hand, Produced, RobberStole
from engine.rules import production
from engine.settings.enums import BuildKind, Resource
from engine.tests.test_dice import (
    INTERVAL,
    make_state,
    of_kind,
    place,
    set_hand,
    totals,
    wp7_registry,
)

ORE, LUMBER, FISH = Resource.ORE, Resource.LUMBER, Resource.FISH
CITY = BuildKind.CITY
V_ORE8 = (31, 30, 32)      # vertices of hex 4 (ore, 8), not touching hex 11
V_LUMBER8 = 51             # hex 11 (lumber, 8), hex 10 (ore, 4), hex 15 (ore, 5)
V_FISH4 = 16               # fishing ground 19 (fish, 4), hex 0 (lumber, 5)


class ProductionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = wp7_registry()
        self._reg.__enter__()
        self.state = make_state(n=3)

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)

    def test_settlement_one_city_two(self) -> None:
        s = self.state
        place(s, 0, V_ORE8[0])
        place(s, 1, V_ORE8[1], CITY)
        place(s, 2, V_LUMBER8, CITY)
        events = production.produce(s, 8, 100)
        self.assertEqual([type(e) for e in events], [Produced, Hand, Hand, Hand])
        prod = events[0]
        self.assertEqual(prod.roll, 8)
        self.assertEqual(prod.gains, {0: {ORE: 1}, 1: {ORE: 2}, 2: {LUMBER: 2}})
        self.assertEqual(prod.skipped, {})
        self.assertEqual([e.seat for e in events[1:]], [0, 1, 2])
        self.assertEqual(events[2].hand[ORE], 2)
        self.assertEqual(s.players[0].hand[ORE], 1)
        self.assertEqual(s.bank[ORE], 19 - 3)
        self.assertEqual(s.bank[LUMBER], 19 - 2)

    def test_same_player_two_buildings_on_one_hex(self) -> None:
        s = self.state
        place(s, 0, V_ORE8[0])
        place(s, 0, V_ORE8[2], CITY)
        events = production.produce(s, 8, 0)
        self.assertEqual(events[0].gains, {0: {ORE: 3}})

    def test_production_amounts_from_settings(self) -> None:
        s = make_state(overrides={"economy": {"production_per": {"settlement": 2, "city": 3}}})
        place(s, 0, V_ORE8[0])
        place(s, 1, V_ORE8[1], CITY)
        self.assertEqual(production.produce(s, 8, 0)[0].gains, {0: {ORE: 2}, 1: {ORE: 3}})

    def test_fishing_ground_produces_fish(self) -> None:
        s = self.state
        place(s, 0, V_FISH4)
        place(s, 1, V_LUMBER8)
        events = production.produce(s, 4, 0)
        self.assertEqual(events[0].gains, {0: {FISH: 1}, 1: {ORE: 1}})
        self.assertEqual(s.players[0].hand[FISH], 1)
        self.assertEqual(s.bank[FISH], 18)

    def test_nothing_without_buildings(self) -> None:
        events = production.produce(self.state, 8, 0)
        self.assertEqual(events, [Produced(at=0, roll=8, gains={}, skipped={})])

    def test_robber_hex_produces_nothing(self) -> None:
        s = self.state
        s.robber_hex = 4
        place(s, 0, V_ORE8[0])
        place(s, 1, V_LUMBER8)
        events = production.produce(s, 8, 0)
        self.assertEqual(events[0].gains, {1: {LUMBER: 1}})
        self.assertEqual(events[0].skipped, {ORE: production.SKIP_ROBBER})
        self.assertEqual(s.players[0].hand[ORE], 0)
        self.assertEqual(s.bank[ORE], 19)

    def test_robber_on_fishing_ground_blocks_fish(self) -> None:
        s = self.state
        s.robber_hex = 19
        place(s, 0, V_FISH4)
        events = production.produce(s, 4, 0)
        self.assertEqual(events[0].gains, {})
        self.assertEqual(events[0].skipped, {FISH: production.SKIP_ROBBER})

    # ----------------------------------------------------------- bank shortage
    def test_bank_has_enough(self) -> None:
        s = self.state
        s.bank[ORE] = 3
        place(s, 0, V_ORE8[0])
        place(s, 1, V_ORE8[1], CITY)
        events = production.produce(s, 8, 0)
        self.assertEqual(events[0].gains, {0: {ORE: 1}, 1: {ORE: 2}})
        self.assertEqual(s.bank[ORE], 0)

    def test_shortage_several_players_nobody_gets_it(self) -> None:
        s = self.state
        s.bank[ORE] = 2
        place(s, 0, V_ORE8[0])
        place(s, 1, V_ORE8[1], CITY)
        place(s, 2, V_LUMBER8)
        events = production.produce(s, 8, 0)
        self.assertEqual(events[0].gains, {2: {LUMBER: 1}})
        self.assertEqual(events[0].skipped, {ORE: production.SKIP_BANK_SHORTAGE})
        self.assertEqual(s.bank[ORE], 2)
        self.assertEqual(s.players[0].hand[ORE] + s.players[1].hand[ORE], 0)
        self.assertEqual([type(e) for e in events], [Produced, Hand])

    def test_shortage_one_player_gets_the_rest(self) -> None:
        s = self.state
        s.bank[ORE] = 2
        place(s, 1, V_ORE8[0], CITY)
        place(s, 1, V_ORE8[1])               # owed 3 in total, all to seat 1
        events = production.produce(s, 8, 0)
        self.assertEqual(events[0].gains, {1: {ORE: 2}})
        self.assertEqual(events[0].skipped, {ORE: production.SKIP_BANK_PARTIAL})
        self.assertEqual(s.bank[ORE], 0)
        self.assertEqual(s.players[1].hand[ORE], 2)

    def test_shortage_one_player_bank_empty(self) -> None:
        s = self.state
        s.bank[ORE] = 0
        place(s, 1, V_ORE8[0])
        events = production.produce(s, 8, 0)
        self.assertEqual(events[0].gains, {})
        self.assertEqual(events[0].skipped, {ORE: production.SKIP_BANK_SHORTAGE})

    def test_shortage_is_per_resource(self) -> None:
        s = self.state
        s.bank[ORE] = 1
        place(s, 0, V_ORE8[0])
        place(s, 1, V_ORE8[1])
        place(s, 0, V_LUMBER8, CITY)
        events = production.produce(s, 8, 0)
        self.assertEqual(events[0].gains, {0: {LUMBER: 2}})
        self.assertEqual(events[0].skipped, {ORE: production.SKIP_BANK_SHORTAGE})

    # ------------------------------------------------------------ via the clock
    def test_roll_through_dice_timer(self) -> None:
        s = make_state(rolls=[[5, 3]])
        place(s, 2, V_ORE8[0], CITY)
        events = game.advance(s, INTERVAL)
        self.assertEqual([type(e) for e in events], [DiceRolled, Produced, Hand])
        self.assertEqual(events[1].gains, {2: {ORE: 2}})
        self.assertEqual(events[1].at, INTERVAL)

    def test_resource_conservation_over_many_rolls(self) -> None:
        for seed in range(4):
            s = make_state(n=4, seed=seed)
            for seat, (v, kind) in enumerate([(31, CITY), (51, BuildKind.SETTLEMENT), (16, CITY), (47, CITY)]):
                place(s, seat, v, kind)
            place(s, 0, 19, CITY)
            place(s, 1, 33, CITY)
            set_hand(s, 3, brick=5, wool=5)
            before = totals(s)
            stolen = 0
            for k in range(1, 401):
                stolen += len(of_kind(game.advance(s, k * INTERVAL), RobberStole))
                self.assertEqual(totals(s), before)
                self.assertTrue(all(n >= 0 for n in s.bank.values()))
                self.assertTrue(all(n >= 0 for p in s.players for n in p.hand.values()))
            self.assertEqual(len(s.dice_history), 400)
            self.assertGreater(stolen, 0)


if __name__ == "__main__":
    unittest.main()
