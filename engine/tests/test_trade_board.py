"""Trade board (stage 2), through ``game.apply`` / ``game.advance`` with every rule module."""
from __future__ import annotations

import unittest

from engine import game
from engine.errors import RuleError
from engine.events import Hand, OfferClosed, OfferPosted
from engine.rules import trade_board
from engine.settings.enums import Resource
from engine.state import GameState
from engine.tests.test_dice import make_state, set_hand
from engine.views import filter_events, project_state


class TradeBoardTest(unittest.TestCase):
    def state(self, trading: dict | None = None) -> GameState:
        s = make_state(overrides={"trading": trading or {}}, stage=2)
        for p in s.players:
            set_hand(s, p.seat)
        return s

    def do(self, s: GameState, seat: int, intent: dict, now: int | None = None) -> list:
        now = max(s.now_ms, 100) if now is None else now
        events = game.advance(s, now)
        return events + game.apply(s, seat, intent, now)

    def code(self, s: GameState, seat: int, intent: dict) -> tuple[str, dict]:
        with self.assertRaises(RuleError) as cm:
            self.do(s, seat, intent)
        return cm.exception.code, cm.exception.params

    def post(self, s: GameState, seat: int, give: dict, get: dict, now: int | None = None) -> int:
        ev = self.do(s, seat, {"a": "post_offer", "give": give, "get": get}, now)
        return next(e for e in ev if isinstance(e, OfferPosted)).offer

    def test_post_and_accept_moves_the_cards(self) -> None:
        s = self.state()
        set_hand(s, 0, brick=2)
        set_hand(s, 1, ore=1, grain=1)
        oid = self.post(s, 0, {"brick": 2}, {"ore": 1, "grain": 1})
        self.assertEqual(project_state(s, 2)["trade_board"]["offers"][0]["give"], {"brick": 2})
        ev = self.do(s, 1, {"a": "accept_offer", "offer": oid})
        closed = next(e for e in ev if isinstance(e, OfferClosed))
        self.assertEqual((closed.reason, closed.by, closed.seat), ("accepted", 1, 0))
        self.assertEqual(s.players[0].hand[Resource.ORE], 1)
        self.assertEqual(s.players[1].hand[Resource.BRICK], 2)
        self.assertEqual((s.players[0].hand_count, s.players[1].hand_count), (2, 2))
        self.assertEqual(trade_board.offers(s), {})
        hands = [e for e in ev if isinstance(e, Hand)]
        self.assertEqual(sorted(h.seat for h in hands), [0, 1])
        seen = [e["k"] for e in filter_events(ev, 2, s)]
        self.assertIn("offer_closed", seen)
        self.assertEqual(self.code(s, 1, {"a": "accept_offer", "offer": oid})[0], "offer.not_found")

    def test_post_refusals(self) -> None:
        s = self.state({"max_open_offers": 1})
        self.assertEqual(self.code(s, 0, {"a": "post_offer", "give": {"wool": 1}, "get": {"ore": 1}}),
                         ("offer.cannot_afford", {"missing": {"wool": 1}}))
        set_hand(s, 0, wool=3)
        self.post(s, 0, {"wool": 1}, {"ore": 1})
        self.assertEqual(self.code(s, 0, {"a": "post_offer", "give": {"wool": 1}, "get": {"ore": 1}}),
                         ("offer.too_many", {"max": 1}))
        s.players[1].setup_done = False
        set_hand(s, 1, wool=1)
        self.assertEqual(self.code(s, 1, {"a": "post_offer", "give": {"wool": 1}, "get": {"ore": 1}})[0],
                         "offer.setup_not_done")
        with self.assertRaises(RuleError) as cm:       # schema: same resource on both sides
            self.do(s, 0, {"a": "post_offer", "give": {"wool": 1}, "get": {"wool": 2}})
        self.assertEqual(cm.exception.code, "command.invalid")

    def test_player_trades_off(self) -> None:
        s = self.state({"player_trades": False})
        set_hand(s, 0, wool=1)
        self.assertEqual(self.code(s, 0, {"a": "post_offer", "give": {"wool": 1}, "get": {"ore": 1}})[0],
                         "offer.disabled")

    def test_accept_refusals(self) -> None:
        s = self.state()
        set_hand(s, 0, wool=2)
        oid = self.post(s, 0, {"wool": 2}, {"ore": 1})
        self.assertEqual(self.code(s, 0, {"a": "accept_offer", "offer": oid})[0], "offer.own")
        self.assertEqual(self.code(s, 1, {"a": "accept_offer", "offer": oid}),
                         ("offer.cannot_afford", {"missing": {"ore": 1}}))
        set_hand(s, 1, ore=1)
        set_hand(s, 0, wool=1)                          # the poster spent a card meanwhile
        self.assertEqual(self.code(s, 1, {"a": "accept_offer", "offer": oid}),
                         ("offer.poster_short", {"missing": {"wool": 1}}))
        self.assertIn(oid, trade_board.offers(s))       # the offer stays up

    def test_cancel(self) -> None:
        s = self.state()
        set_hand(s, 0, wool=1)
        oid = self.post(s, 0, {"wool": 1}, {"ore": 1})
        self.assertEqual(self.code(s, 1, {"a": "cancel_offer", "offer": oid})[0], "offer.not_yours")
        ev = self.do(s, 0, {"a": "cancel_offer", "offer": oid})
        self.assertEqual(next(e for e in ev if isinstance(e, OfferClosed)).reason, "cancelled")
        self.assertEqual(trade_board.offers(s), {})

    def test_offers_expire(self) -> None:
        s = self.state({"offer_expiry_ms": 5000})
        set_hand(s, 0, wool=2)
        start = s.now_ms + 100
        a = self.post(s, 0, {"wool": 1}, {"ore": 1}, now=start)
        b = self.post(s, 0, {"wool": 1}, {"grain": 1}, now=start + 10)
        self.do(s, 0, {"a": "cancel_offer", "offer": b}, now=start + 20)
        ev = game.advance(s, start + 5000)
        closed = [e for e in ev if isinstance(e, OfferClosed)]
        self.assertEqual([(c.offer, c.reason) for c in closed], [(a, "expired")])
        self.assertEqual(trade_board.offers(s), {})

    def test_resigning_takes_offers_down(self) -> None:
        s = self.state()
        set_hand(s, 0, wool=1)
        oid = self.post(s, 0, {"wool": 1}, {"ore": 1})
        ev = self.do(s, 0, {"a": "resign"})
        closed = [e for e in ev if isinstance(e, OfferClosed)]
        self.assertEqual([(c.offer, c.reason) for c in closed], [(oid, "resigned")])


if __name__ == "__main__":
    unittest.main()
