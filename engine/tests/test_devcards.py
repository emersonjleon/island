"""Development cards and Largest Army (stage 2), through ``game.apply`` with every rule module."""
from __future__ import annotations

import unittest

from engine import game
from engine.board import coords
from engine.errors import RuleError
from engine.events import DevCardBought, DevCardPlayed, LargestArmy, Points, RobberMoved
from engine.rules import devcards, placement
from engine.settings.enums import BuildKind, DevCardKind, Resource
from engine.state import GameState
from engine.tests.test_dice import make_state, place, set_hand
from engine.views import filter_events, project_state

ALL_KNIGHTS = {"dev_cards": {"deck": {"knight": 10, "victory_point": 0, "road_building": 0,
                                      "year_of_plenty": 0, "monopoly": 0}}}


def deck_of(kind: str, n: int = 5) -> dict:
    return {"dev_cards": {"deck": {k.value: (n if k.value == kind else 0) for k in DevCardKind}}}


class DevCardTest(unittest.TestCase):
    def state(self, overrides: dict | None = None) -> GameState:
        s = make_state(overrides=overrides, stage=2)
        for p in s.players:
            set_hand(s, p.seat)          # empty hands, cards back to the bank
        return s

    def tick(self, s: GameState, now: int | None) -> int:
        return max(s.now_ms, 100) if now is None else now

    def buy(self, s: GameState, seat: int, now: int | None = None) -> list:
        set_hand(s, seat, wool=1, grain=1, ore=1)
        return game.apply(s, seat, {"a": "buy_dev_card"}, self.tick(s, now))

    def roll(self, s: GameState) -> None:
        s.dice_history.append(8)                  # what the cooldown counts

    def play(self, s: GameState, seat: int, card: str, now: int | None = None, **fields) -> list:
        now = max(s.now_ms, 200) if now is None else now
        return game.apply(s, seat, {"a": "play_dev_card", "card": card, **fields}, now)

    def code(self, fn, *args, **kw) -> str:
        with self.assertRaises(RuleError) as cm:
            fn(*args, **kw)
        return cm.exception.code

    # ------------------------------------------------------------ buying
    def test_buy_pays_the_bank_and_draws_a_card(self) -> None:
        s = self.state(deck_of("monopoly", 2))
        bank_before = dict(s.bank)
        ev = self.buy(s, 0)
        self.assertEqual(s.players[0].hand_count, 0)
        self.assertEqual(s.bank[Resource.ORE], bank_before[Resource.ORE])   # 1 ore out to the hand, back in
        bought = [e for e in ev if isinstance(e, DevCardBought)]
        self.assertEqual((bought[0].card, bought[0].deck_left), (DevCardKind.MONOPOLY, 1))
        self.assertEqual([c["kind"] for c in devcards.hand(s, 0)], ["monopoly"])
        self.buy(s, 1)
        self.assertEqual(self.code(self.buy, s, 2), "dev.deck_empty")

    def test_buy_refusals(self) -> None:
        s = self.state()
        self.assertEqual(self.code(game.apply, s, 0, {"a": "buy_dev_card"}, 1), "dev.cannot_afford")
        s.players[1].setup_done = False
        self.assertEqual(self.code(self.buy, s, 1), "dev.setup_not_done")

    def test_others_see_a_purchase_without_the_card(self) -> None:
        s = self.state(deck_of("knight"))
        ev = [e for e in self.buy(s, 0) if isinstance(e, DevCardBought)]
        self.assertEqual(filter_events(ev, 0, s)[0]["card"], "knight")
        self.assertNotIn("card", filter_events(ev, 1, s)[0])
        mine = project_state(s, 0)["dev_cards"]["players"]["0"]
        theirs = project_state(s, 1)["dev_cards"]["players"]["0"]
        self.assertEqual(mine["cards"][0]["kind"], "knight")
        self.assertEqual((theirs.get("cards"), theirs["count"]), (None, 1))

    # ------------------------------------------------------------ cooldown
    def test_one_card_per_roll_and_not_the_one_just_bought(self) -> None:
        s = self.state(deck_of("victory_point"))
        self.buy(s, 0)
        self.buy(s, 0)
        self.assertEqual(self.code(self.play, s, 0, "victory_point"), "dev.too_new")
        self.roll(s)
        self.play(s, 0, "victory_point")
        self.assertEqual(self.code(self.play, s, 0, "victory_point"), "dev.cooldown")
        self.roll(s)
        self.play(s, 0, "victory_point")
        self.assertEqual(s.players[0].points, 2)
        self.assertEqual(self.code(self.play, s, 0, "victory_point"), "dev.no_card")

    def test_cooldown_in_ms(self) -> None:
        s = self.state({**deck_of("victory_point"),
                        "dev_cards": {**deck_of("victory_point")["dev_cards"], "cooldown": "ms", "cooldown_ms": 5000}})
        self.buy(s, 0, now=1000)
        self.buy(s, 0, now=1000)
        self.assertEqual(self.code(self.play, s, 0, "victory_point", now=5999), "dev.too_new")
        self.play(s, 0, "victory_point", now=6000)
        self.assertEqual(self.code(self.play, s, 0, "victory_point", now=10999), "dev.cooldown")
        self.play(s, 0, "victory_point", now=11000)

    def test_victory_points_counted_on_purchase_when_not_played(self) -> None:
        cfg = deck_of("victory_point")
        cfg["dev_cards"]["vp_cards_must_be_played"] = False
        s = self.state(cfg)
        ev = self.buy(s, 0)
        self.assertIn(Points(at=100, seat=0, points=1), ev)
        self.roll(s)
        self.assertEqual(self.code(self.play, s, 0, "victory_point"), "dev.not_playable")

    def test_victory_point_card_can_win(self) -> None:
        s = self.state({**deck_of("victory_point"), "victory": {"target": 5}})
        s.players[2].points = 4
        self.buy(s, 2)
        self.roll(s)
        self.play(s, 2, "victory_point")
        self.assertEqual((s.phase, s.winner), ("finished", 2))

    # ------------------------------------------------------------ cards
    def test_road_building_gives_free_roads(self) -> None:
        s = self.state(deck_of("road_building"))
        self.buy(s, 0)
        self.roll(s)
        self.play(s, 0, "road_building")
        self.assertEqual(placement.free_roads(s, 0), 2)
        self.assertEqual(placement.build_cost(s, 0, BuildKind.ROAD), {r: 0 for r in Resource})
        self.assertEqual(placement.build_cost(s, 1, BuildKind.ROAD), placement.cost_of(s, BuildKind.ROAD))

    def test_year_of_plenty_takes_from_the_bank(self) -> None:
        s = self.state(deck_of("year_of_plenty"))
        self.buy(s, 1)
        self.roll(s)
        self.assertEqual(self.code(self.play, s, 1, "year_of_plenty", resources=["ore"]), "dev.need_resources")
        s.bank[Resource.BRICK] = 1
        self.assertEqual(self.code(self.play, s, 1, "year_of_plenty", resources=["brick", "brick"]),
                         "dev.bank_short")
        ev = self.play(s, 1, "year_of_plenty", resources=["ore", "brick"])
        self.assertEqual(s.players[1].hand[Resource.ORE], 1)
        self.assertEqual(s.bank[Resource.BRICK], 0)
        self.assertIn("took", filter_events([e for e in ev if isinstance(e, DevCardPlayed)], 2, s)[0])

    def test_monopoly_takes_every_card_of_one_resource(self) -> None:
        s = self.state(deck_of("monopoly"))
        self.buy(s, 0)
        self.roll(s)
        set_hand(s, 1, wool=3, ore=1)
        set_hand(s, 2, wool=2)
        self.assertEqual(self.code(self.play, s, 0, "monopoly"), "dev.need_resource")
        ev = self.play(s, 0, "monopoly", resource="wool")
        played = next(e for e in ev if isinstance(e, DevCardPlayed))
        self.assertEqual(played.taken, {1: 3, 2: 2})
        self.assertEqual((s.players[0].hand[Resource.WOOL], s.players[1].hand_count), (5, 1))

    # ------------------------------------------------------------ knight
    def hex_at(self, s: GameState, dist: int) -> int:
        board = s.board.board
        start = s.robber_hex
        return next(h for h in range(len(board.hexes))
                    if board.is_land(h) and coords.hex_distance(board.hexes[start], board.hexes[h]) == dist)

    def knight_ready(self, s: GameState, seat: int = 0) -> None:
        self.buy(s, seat)
        self.roll(s)

    def test_knight_moves_the_robber_and_steals(self) -> None:
        s = self.state(ALL_KNIGHTS)
        self.knight_ready(s)
        h = self.hex_at(s, 2)
        v = s.board.board.hex_vertices[h][0]
        place(s, 1, v)
        set_hand(s, 1, brick=2)
        start = s.robber_hex
        ev = self.play(s, 0, "knight", hex=h)
        self.assertEqual(s.robber_hex, h)
        self.assertIn(RobberMoved(at=200, from_hex=start, to_hex=h), ev)
        played = next(e for e in ev if isinstance(e, DevCardPlayed))
        self.assertEqual((played.victim, played.stolen), (1, 1))
        self.assertEqual((s.players[0].hand[Resource.BRICK], s.players[1].hand[Resource.BRICK]), (1, 1))
        self.assertEqual(devcards.knights(s)[0], 1)

    def test_knight_refusals(self) -> None:
        s = self.state(ALL_KNIGHTS)
        self.knight_ready(s)
        self.assertEqual(self.code(self.play, s, 0, "knight"), "dev.need_hex")
        self.assertEqual(self.code(self.play, s, 0, "knight", hex=s.robber_hex), "dev.bad_hex")
        far = self.hex_at(s, 2)
        s.settings = s.settings.model_copy(update={"robber": s.settings.robber.model_copy(
            update={"knight_max_distance": 1})})
        self.assertEqual(self.code(self.play, s, 0, "knight", hex=far), "dev.too_far")
        h = self.hex_at(s, 1)
        verts = s.board.board.hex_vertices[h]
        place(s, 1, verts[0])
        place(s, 2, verts[3])
        set_hand(s, 1, ore=1)
        set_hand(s, 2, ore=1)
        err = None
        try:
            self.play(s, 0, "knight", hex=h)
        except RuleError as exc:
            err = exc
        self.assertEqual((err.code, err.params), ("dev.need_victim", {"choices": [1, 2]}))
        self.assertEqual(self.code(self.play, s, 0, "knight", hex=h, victim=0), "dev.bad_victim")
        self.play(s, 0, "knight", hex=h, victim=2)
        self.assertEqual(s.players[2].hand_count, 0)

    def test_largest_army(self) -> None:
        s = self.state(ALL_KNIGHTS)
        events = []
        for _ in range(3):
            self.buy(s, 0)
            self.roll(s)
            events = self.play(s, 0, "knight", hex=self.hex_at(s, 1))
        self.assertIn(LargestArmy(at=200, seat=0, previous=None, knights={0: 3, 1: 0, 2: 0}), events)
        self.assertEqual((devcards.army_holder(s), s.players[0].points), (0, 2))
        for _ in range(3):                                  # a tie keeps it with seat 0
            self.buy(s, 1)
            self.roll(s)
            self.play(s, 1, "knight", hex=self.hex_at(s, 1))
        self.assertEqual(devcards.army_holder(s), 0)
        self.buy(s, 1)
        self.roll(s)
        self.play(s, 1, "knight", hex=self.hex_at(s, 1))
        self.assertEqual((devcards.army_holder(s), s.players[0].points, s.players[1].points), (1, 0, 2))
        self.assertEqual(project_state(s, None)["dev_cards"]["army"], 1)


if __name__ == "__main__":
    unittest.main()
