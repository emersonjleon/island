"""Advanced developments (ages): tier decks, the new cards and effects that last a few rolls."""
from __future__ import annotations

import unittest
from typing import Any

from engine import game
from engine.board import coords
from engine.errors import RuleError
from engine.events import DevCardBought, DevCardPlayed, LargestArmy
from engine.rules import dev_effects, devcards, placement, production, trade
from engine.settings.enums import BuildKind, DevCardKind, Resource
from engine.sim.invariants import resource_totals
from engine.state import GameState
from engine.tests.test_ages import FISHING_HEX, FISHING_VERTEX, new_state, set_age
from engine.tests.test_dice import make_state, place, set_hand

TIER2 = dict(wool=1, grain=1, ore=1, fish=1)
TIER3 = dict(wool=1, grain=1, ore=1, fish=2)


def only(kind: str, n: int = 3) -> dict[str, int]:
    return {k.value: (n if k.value == kind else 0) for k in DevCardKind}


def fresh(overrides: dict[str, Any] | None = None) -> GameState:
    s = new_state(overrides)
    for p in s.players:
        set_hand(s, p.seat)
    return s


def give(s: GameState, seat: int, kind: str, tier: int = 2) -> None:
    """Put a card straight into ``seat``'s hand, old enough to play."""
    devcards._ext(s)["hands"].setdefault(str(seat), []).append({"kind": kind, "at": 0, "roll": -1, "tier": tier})


def play(s: GameState, seat: int, card: str, **fields: Any) -> list[Any]:
    return game.apply(s, seat, {"a": "play_dev_card", "card": card, **fields}, max(s.now_ms, 100))


def code(fn: Any, *args: Any, **kw: Any) -> tuple[str, dict[str, Any]]:
    try:
        fn(*args, **kw)
    except RuleError as exc:
        return exc.code, dict(exc.params)
    raise AssertionError("no reject")


def played(events: list[Any]) -> DevCardPlayed:
    return next(e for e in events if isinstance(e, DevCardPlayed))


class BuyTierTest(unittest.TestCase):
    def buy(self, s: GameState, seat: int, tier: int) -> list[Any]:
        return game.apply(s, seat, {"a": "buy_dev_card", "tier": tier}, 100)

    def test_tiers_follow_the_buyers_age(self) -> None:
        s = fresh()
        set_hand(s, 0, **TIER2)
        self.assertEqual(code(self.buy, s, 0, 2), ("dev.tier_locked", {"tier": 2, "age": 1}))
        set_age(s, 0, 2)
        bank = dict(s.bank)
        ev = self.buy(s, 0, 2)
        bought = next(e for e in ev if isinstance(e, DevCardBought))
        self.assertEqual(bought.tier, 2)
        self.assertIn(bought.card, s.settings.dev_cards.deck_tier2)
        self.assertEqual(s.bank[Resource.FISH], bank[Resource.FISH] + 1)
        self.assertEqual(devcards.hand(s, 0)[0]["tier"], 2)
        self.assertEqual(sum(devcards.deck_left(s, 2).values()), sum(s.settings.dev_cards.deck_tier2.values()) - 1)
        set_hand(s, 0, **TIER3)
        self.assertEqual(code(self.buy, s, 0, 3)[0], "dev.tier_locked")
        set_age(s, 0, 3)
        self.buy(s, 0, 3)
        self.assertEqual(s.players[0].hand_count, 0)

    def test_tiers_need_ages_and_the_setting(self) -> None:
        s = make_state(stage=3, clock=False)
        set_hand(s, 0, **TIER2)
        self.assertEqual(code(self.buy, s, 0, 2), ("dev.no_tiers", {"tier": 2}))
        off = fresh({"ages": {"dev_tiers": False}})
        set_age(off, 0, 2)
        set_hand(off, 0, **TIER2)
        self.assertEqual(code(self.buy, off, 0, 2)[0], "dev.no_tiers")

    def test_each_tier_refills_its_own_deck(self) -> None:
        s = fresh({"dev_cards": {"deck_tier2": only("merchant", 1)}})
        set_age(s, 0, 2)
        for _ in range(2):
            set_hand(s, 0, **TIER2)
            ev = self.buy(s, 0, 2)
            self.assertEqual(next(e for e in ev if isinstance(e, DevCardBought)).card, DevCardKind.MERCHANT)
        self.assertEqual(sum(devcards.deck_left(s, 1).values()), sum(s.settings.dev_cards.deck.values()))

    def test_view_counts_cards_per_tier(self) -> None:
        s = fresh()
        give(s, 0, "merchant", 2)
        give(s, 0, "tribute", 3)
        view = devcards.state_view(s, 1)
        self.assertEqual(view["players"]["0"]["tiers"], {"1": 0, "2": 1, "3": 1})
        self.assertNotIn("cards", view["players"]["0"])
        self.assertEqual(set(view["decks_left"]), {"1", "2", "3"})
        plain = make_state(stage=3, clock=False)
        self.assertNotIn("decks_left", devcards.state_view(plain, 0))


class EffectTest(unittest.TestCase):
    def test_merchant_gives_two_to_one_for_three_rolls(self) -> None:
        s = fresh()
        give(s, 0, "merchant")
        self.assertEqual(trade.best_ratio(s, 0, Resource.WOOL)[0], 4)
        ev = play(s, 0, "merchant")
        self.assertEqual(played(ev).rolls, 3)
        self.assertEqual(trade.best_ratio(s, 0, Resource.WOOL)[0], 2)
        self.assertEqual(trade.best_ratio(s, 1, Resource.WOOL)[0], 4)
        self.assertEqual(devcards.state_view(s, 2)["players"]["0"]["effects"], {"merchant": 3})
        for left in (2, 1, 0):
            s.dice_history.append(8)
            self.assertEqual(dev_effects.left(s, 0, DevCardKind.MERCHANT), left)
        self.assertEqual(trade.best_ratio(s, 0, Resource.WOOL)[0], 4)

    def test_playing_the_same_effect_again_adds_rolls_up_to_the_cap(self) -> None:
        s = fresh()
        dev_effects.add(s, 0, DevCardKind.GREAT_MARKET, 5)
        s.dice_history.append(8)                                # 4 left
        dev_effects.add(s, 0, DevCardKind.GREAT_MARKET, 5)      # 9 left, under the cap of 10
        self.assertEqual(dev_effects.left(s, 0, DevCardKind.GREAT_MARKET), 9)
        dev_effects.add(s, 0, DevCardKind.GREAT_MARKET, 5)      # capped at 200 %
        self.assertEqual(dev_effects.left(s, 0, DevCardKind.GREAT_MARKET), 10)

    def test_fishing_fleet_adds_fish_for_the_next_rolls(self) -> None:
        s = fresh()
        place(s, 0, FISHING_VERTEX)
        roll = s.board.token[FISHING_HEX]
        give(s, 0, "fishing_fleet")
        play(s, 0, "fishing_fleet")
        for _ in range(3):
            s.dice_history.append(roll)                         # the roll being produced
            self.assertEqual(production.owed_by_resource(s, roll)[0][Resource.FISH][0], 2)
        s.dice_history.append(roll)
        self.assertEqual(production.owed_by_resource(s, roll)[0][Resource.FISH][0], 1)

    def test_architect_takes_cards_off_the_next_city(self) -> None:
        s = fresh()
        give(s, 0, "architect", 3)
        self.assertEqual(code(play, s, 0, "architect", resources=["fish", "ore"])[0], "dev.no_fish_discount")
        self.assertEqual(code(play, s, 0, "architect", resources=["ore"]), ("dev.need_resources", {"count": 2}))
        ev = play(s, 0, "architect", resources=["ore", "ore"])
        self.assertEqual(played(ev).discount, {Resource.ORE: 2})
        self.assertEqual(placement.build_cost(s, 0, BuildKind.CITY)[Resource.ORE], 1)
        self.assertEqual(placement.build_cost(s, 0, BuildKind.SETTLEMENT), placement.cost_of(s, BuildKind.SETTLEMENT))
        v = next(v for v in range(len(s.board.board.vertices)) if s.board.board.land_vertex(v)
                 and placement.settlement_error(s, 0, v, placement.SETUP) is None)
        place(s, 0, v)
        set_hand(s, 0, grain=2, ore=1)
        game.apply(s, 0, {"a": "build", "kind": "city", "vertex": v}, 200)
        self.assertEqual(s.players[0].hand_count, 0)
        self.assertFalse(dev_effects.active(s, 0, DevCardKind.ARCHITECT))
        self.assertEqual(placement.build_cost(s, 0, BuildKind.CITY)[Resource.ORE], 3)


class InstantCardTest(unittest.TestCase):
    def test_causeway_gives_three_free_roads(self) -> None:
        s = fresh()
        give(s, 0, "causeway")
        self.assertEqual(played(play(s, 0, "causeway")).roads, 3)
        self.assertEqual(placement.free_roads(s, 0), 3)

    def test_bountiful_harvest_takes_three_with_at_most_one_fish(self) -> None:
        s = fresh()
        give(s, 0, "bountiful_harvest")
        self.assertEqual(code(play, s, 0, "bountiful_harvest", resources=["fish", "fish", "ore"]),
                         ("dev.too_much_fish", {"max": 1}))
        ev = play(s, 0, "bountiful_harvest", resources=["fish", "ore", "ore"])
        self.assertEqual(played(ev).took, {Resource.FISH: 1, Resource.ORE: 2})
        self.assertEqual(s.players[0].hand_count, 3)

    def test_tribute_takes_cards_only_from_players_ahead(self) -> None:
        s = fresh()
        s.players[1].points, s.players[2].points = 5, 1
        s.players[0].points = 2
        set_hand(s, 1, lumber=2)
        set_hand(s, 2, brick=4)
        give(s, 0, "tribute", 3)
        totals = resource_totals(s)
        ev = play(s, 0, "tribute")
        self.assertEqual(played(ev).taken, {1: 2})                 # had only 2 of the 3
        self.assertEqual(s.players[0].hand[Resource.LUMBER], 2)
        self.assertEqual(s.players[2].hand[Resource.BRICK], 4)     # behind: untouched
        self.assertEqual(resource_totals(s), totals)

    def test_tribute_takes_three_from_each_player_ahead(self) -> None:
        s = fresh()
        s.players[1].points = s.players[2].points = 4
        for seat in (1, 2):
            set_hand(s, seat, wool=5)
        give(s, 0, "tribute", 3)
        self.assertEqual(played(play(s, 0, "tribute")).taken, {1: 3, 2: 3})
        self.assertEqual(s.players[0].hand[Resource.WOOL], 6)


class StrongKnightTest(unittest.TestCase):
    def hex_at(self, s: GameState, dist: int) -> int:
        board = s.board.board
        start = s.robber_hex
        return next(h for h in range(len(board.hexes)) if board.is_land(h) and h not in s.board.fishing
                    and coords.hex_distance(board.hexes[start], board.hexes[h]) == dist)

    def test_veteran_reaches_further_and_robs_hoarders_harder(self) -> None:
        s = fresh({"robber": {"knight_max_distance": 1}, "dev_cards": {"veteran_max_distance": 2}})
        h = self.hex_at(s, 2)
        place(s, 1, s.board.board.hex_vertices[h][0])
        give(s, 0, "knight", 1)
        self.assertEqual(code(play, s, 0, "knight", hex=h)[0], "dev.too_far")
        set_hand(s, 1, brick=8)                                   # over the limit of 7
        give(s, 0, "veteran_knight")
        self.assertEqual(played(play(s, 0, "veteran_knight", hex=h)).stolen, 2)
        self.assertEqual(devcards.knights(s)[0], 1)

    def test_strong_knights_take_one_card_from_a_careful_saver(self) -> None:
        s = fresh()
        h = self.hex_at(s, 2)
        place(s, 1, s.board.board.hex_vertices[h][0])
        set_hand(s, 1, fish=7)                                    # at the limit: safe from the second card
        give(s, 0, "elite_knight", 3)
        self.assertEqual(played(play(s, 0, "elite_knight", hex=h)).stolen, 1)

    def test_every_knight_counts_one_for_the_army(self) -> None:
        s = fresh()
        for i, kind in enumerate(("knight", "veteran_knight", "elite_knight")):
            give(s, 0, kind)
            h = self.hex_at(s, 1)
            ev = play(s, 0, kind, hex=h)
            s.dice_history.append(8)                              # one card per roll
            army = next(e for e in ev if isinstance(e, LargestArmy))
            self.assertEqual(army.knights[0], i + 1)
        self.assertEqual(devcards.army_holder(s), 0)


if __name__ == "__main__":
    unittest.main()
