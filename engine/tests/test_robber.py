"""WP7 robber tests (fixture board: desert 9 has six land neighbours; hex 0 has land
neighbours 1, 3, 4, the fishing ground 19 and plain sea 20, 23)."""
from __future__ import annotations

import unittest

from engine import game
from engine.board.model import GeneratedBoard
from engine.board.topology import Board
from engine.events import DiceRolled, Hand, Produced, RobberMoved, RobberStole
from engine.rules import robber
from engine.settings.enums import Resource, Terrain
from engine.tests.test_dice import (
    INTERVAL,
    make_state,
    of_kind,
    place,
    set_hand,
    totals,
    wp7_registry,
)

V_DESERT = 47     # vertex of the desert (hex 9) and hexes 8, 13
V_FAR = 16        # far from the desert (hexes 0, 19, 23)


class RobberTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = wp7_registry()
        self._reg.__enter__()

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)

    def test_seven_steals_half_from_players_over_limit(self) -> None:
        s = make_state(n=4, rolls=[[3, 4]])
        set_hand(s, 0, lumber=8)                       # 8 > 7 -> loses 4
        set_hand(s, 1, ore=7)                          # not over the limit
        set_hand(s, 2, wool=5, grain=4)                # 9 -> loses 4
        set_hand(s, 3, brick=10, fish=5)               # 15 -> loses 7
        before = totals(s)
        bank_before = dict(s.bank)
        events = game.advance(s, INTERVAL)
        self.assertEqual([type(e) for e in events],
                         [DiceRolled, RobberStole, Hand, RobberStole, Hand, RobberStole, Hand, RobberMoved])
        stole = of_kind(events, RobberStole)
        self.assertEqual([e.seat for e in stole], [0, 2, 3])
        self.assertEqual([sum(e.lost.values()) for e in stole], [4, 4, 7])
        self.assertEqual(stole[0].lost, {Resource.LUMBER: 4})
        self.assertEqual([p.hand_count for p in s.players], [4, 7, 5, 8])
        self.assertEqual(of_kind(events, Produced), [])
        # stolen cards went back to the bank
        lost_total = {r: sum(e.lost.get(r, 0) for e in stole) for r in Resource}
        self.assertEqual(s.bank, {r: bank_before[r] + lost_total[r] for r in Resource})
        self.assertEqual(totals(s), before)
        for e in of_kind(events, Hand):
            self.assertEqual(e.hand, s.players[e.seat].hand)

    def test_steal_count_rounding(self) -> None:
        s = make_state()
        self.assertEqual([robber.steal_count(s, n) for n in (0, 1, 7, 8, 9, 15)], [0, 0, 3, 4, 4, 7])
        s = make_state(overrides={"robber": {"steal_pct": 30}})
        self.assertEqual(robber.steal_count(s, 10), 3)
        self.assertEqual(robber.steal_count(s, 9), 2)
        s = make_state(overrides={"robber": {"steal_rounding": "ceil"}}, stage=3)
        self.assertEqual(robber.steal_count(s, 9), 5)
        self.assertEqual(robber.steal_count(s, 1), 1)

    def test_card_limit_from_settings(self) -> None:
        s = make_state(overrides={"robber": {"card_limit": 3}})
        set_hand(s, 0, lumber=4)
        set_hand(s, 1, lumber=3)
        self.assertEqual(robber.targets(s, s.robber_hex), [0])

    def test_require_adjacent_and_over_limit(self) -> None:
        s = make_state(overrides={"robber": {"require_adjacent": True}})
        place(s, 0, V_DESERT)
        place(s, 1, V_FAR)
        place(s, 2, 33)              # 33 touches the desert too
        set_hand(s, 0, lumber=8)    # adjacent, over
        set_hand(s, 1, lumber=9)    # over, not adjacent
        set_hand(s, 2, lumber=3)    # adjacent, under
        self.assertEqual(robber.targets(s, 9), [0])
        events = robber.on_seven(s, 0)
        self.assertEqual([e.seat for e in of_kind(events, RobberStole)], [0])
        self.assertEqual([p.hand_count for p in s.players], [4, 9, 3])

    def test_require_adjacent_without_over_limit(self) -> None:
        s = make_state(overrides={"robber": {"require_adjacent": True, "require_over_limit": False}})
        place(s, 0, V_DESERT)
        place(s, 1, V_FAR)
        place(s, 2, 33)
        set_hand(s, 0, lumber=8)
        set_hand(s, 1, lumber=9)
        set_hand(s, 2, lumber=3)
        self.assertEqual(robber.targets(s, 9), [0, 2])
        robber.on_seven(s, 0)
        self.assertEqual([p.hand_count for p in s.players], [4, 9, 2])

    def test_no_flags_robs_everyone(self) -> None:
        s = make_state(overrides={"robber": {"require_over_limit": False}})
        set_hand(s, 0, ore=2)
        set_hand(s, 1, ore=1)        # loses floor(0.5) = 0 -> no event
        events = robber.on_seven(s, 0)
        self.assertEqual([e.seat for e in of_kind(events, RobberStole)], [0])
        self.assertEqual(robber.targets(s, 9), [0, 1, 2])

    def test_adjacency_judged_before_the_move(self) -> None:
        for seed in range(10):
            s = make_state(seed=seed, overrides={"robber": {"require_adjacent": True}})
            place(s, 0, V_DESERT)
            set_hand(s, 0, grain=10)
            events = robber.on_seven(s, 0)
            self.assertEqual(s.players[0].hand_count, 5)
            self.assertNotEqual(s.robber_hex, 9)
            self.assertEqual([type(e) for e in events], [RobberStole, Hand, RobberMoved])

    def test_adjacency_after_move(self) -> None:
        s = make_state(overrides={"robber": {"require_adjacent": True, "adjacency_timing": "after_move"}},
                       stage=3)
        place(s, 0, V_DESERT)                # touches 9, 8, 13
        set_hand(s, 0, grain=10)
        events = robber.on_seven(s, 0)
        self.assertIsInstance(events[0], RobberMoved)
        lost = s.players[0].hand_count < 10
        self.assertEqual(lost, s.robber_hex in (8, 13))

    def test_stolen_cards_vanish_when_not_to_bank(self) -> None:
        s = make_state(overrides={"robber": {"stolen_to_bank": False}}, stage=3)
        set_hand(s, 0, ore=10)
        bank = dict(s.bank)
        robber.on_seven(s, 0)
        self.assertEqual(s.bank, bank)
        self.assertEqual(s.players[0].hand_count, 5)

    def test_steal_is_random_and_from_the_hand(self) -> None:
        seen: set[tuple[int, int]] = set()
        for seed in range(30):
            s = make_state(seed=seed)
            set_hand(s, 0, lumber=4, ore=4)
            robber.on_seven(s, 0)
            h = s.players[0].hand
            self.assertEqual(h[Resource.LUMBER] + h[Resource.ORE], 4)
            seen.add((h[Resource.LUMBER], h[Resource.ORE]))
        self.assertGreater(len(seen), 2)

    def test_robber_disabled(self) -> None:
        s = make_state(overrides={"robber": {"enabled": False}})
        set_hand(s, 0, ore=10)
        self.assertEqual(robber.on_seven(s, 0), [])
        self.assertEqual(s.players[0].hand_count, 10)
        self.assertEqual(s.robber_hex, 9)

    # -------------------------------------------------------------- movement
    def test_moves_to_random_land_neighbour(self) -> None:
        reached: set[int] = set()
        for seed in range(40):
            s = make_state(seed=seed)
            s.robber_hex = 0
            events = robber.on_seven(s, 0)
            self.assertEqual(events, [RobberMoved(at=0, from_hex=0, to_hex=s.robber_hex)])
            reached.add(s.robber_hex)  # type: ignore[arg-type]
        self.assertEqual(reached, {1, 3, 4})       # never sea 20/23, never fishing ground 19

    def test_from_desert_reaches_all_neighbours(self) -> None:
        reached = set()
        for seed in range(60):
            s = make_state(seed=seed)
            robber.on_seven(s, 0)
            reached.add(s.robber_hex)
        self.assertEqual(reached, {13, 14, 10, 5, 4, 8})

    def test_may_enter_fishing(self) -> None:
        reached = set()
        for seed in range(60):
            s = make_state(seed=seed, overrides={"robber": {"may_enter_fishing": True}}, stage=3)
            s.robber_hex = 0
            robber.on_seven(s, 0)
            reached.add(s.robber_hex)
        self.assertEqual(reached, {1, 3, 4, 19})

    def test_may_not_enter_desert(self) -> None:
        s = make_state(overrides={"robber": {"may_enter_desert": False}})
        self.assertEqual(robber.legal_neighbours(s, 4), [8, 5, 1, 0, 3])
        for seed in range(40):
            s = make_state(seed=seed, overrides={"robber": {"may_enter_desert": False}})
            s.robber_hex = 4
            robber.on_seven(s, 0)
            self.assertNotEqual(s.robber_hex, 9)

    def test_stays_without_legal_neighbour(self) -> None:
        topo = Board.spiral_island(1, sea_margin=1)
        sea = len(topo.hexes) - 1
        gb = GeneratedBoard(board=topo, terrain=(Terrain.FOREST,) + (None,) * sea, token=(5,) + (None,) * sea,
                            fishing=frozenset(), harbors=(), robber_start=0)
        s = make_state(board=gb)
        events = robber.on_seven(s, 0)
        self.assertEqual(events, [RobberMoved(at=0, from_hex=0, to_hex=0)])
        self.assertEqual(s.robber_hex, 0)

    def test_moved_robber_blocks_next_production(self) -> None:
        s = make_state(rolls=[[3, 4]])
        game.advance(s, INTERVAL)
        moved_to = s.robber_hex
        self.assertNotEqual(moved_to, 9)
        token = s.board.token[moved_to]  # type: ignore[index]
        place(s, 0, s.board.board.hex_vertices[moved_to][0])  # type: ignore[index]
        from engine.rules import production
        events = production.produce(s, token, 0)  # type: ignore[arg-type]
        self.assertNotIn(0, events[0].gains)


if __name__ == "__main__":
    unittest.main()
