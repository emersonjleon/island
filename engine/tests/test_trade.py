"""WP7 bank/harbor trade tests (fixture board: generic 3:1 harbor on vertices 16 and 7,
lumber 2:1 harbor on vertices 43 and 58)."""
from __future__ import annotations

import unittest

from engine import game
from engine.commands import BankTrade
from engine.errors import RuleError
from engine.events import Hand, Traded
from engine.rules import trade
from engine.settings.enums import BuildKind, Resource
from engine.state import Construction
from engine.tests.test_dice import make_state, place, set_hand, totals, wp7_registry

L, O, W = Resource.LUMBER, Resource.ORE, Resource.WOOL
GENERIC_V = (16, 7)
LUMBER_V = (43, 58)


def bt(give: dict[str, int], get: dict[str, int]) -> dict:
    return {"t": "intent", "cid": "c1", "a": "bank_trade", "give": give, "get": get}


class TradeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = wp7_registry()
        self._reg.__enter__()
        game.set_check_rejects(True)
        self.s = make_state(clock=False)
        self.now = 1000
        game.advance(self.s, self.now)

    def tearDown(self) -> None:
        game.set_check_rejects(False)
        self._reg.__exit__(None, None, None)

    def reject(self, code: str, cmd: object, seat: int = 0) -> RuleError:
        before = totals(self.s)
        with self.assertRaises(RuleError) as cm:
            game.apply(self.s, seat, cmd, self.now)
        self.assertEqual(cm.exception.code, code)
        self.assertEqual(totals(self.s), before)
        return cm.exception

    def test_bank_four_to_one(self) -> None:
        set_hand(self.s, 0, lumber=5)
        events = game.apply(self.s, 0, bt({"lumber": 4}, {"ore": 1}), self.now)
        self.assertEqual(events, [
            Traded(at=self.now, seat=0, give={L: 4}, get={O: 1}, ratio=4, via="bank"),
            Hand(at=self.now, seat=0, hand=self.s.players[0].hand),
        ])
        self.assertEqual(self.s.players[0].hand[L], 1)
        self.assertEqual(self.s.players[0].hand[O], 1)
        self.assertEqual(self.s.bank[L], 18)          # 19 - 5 dealt + 4 returned
        self.assertEqual(self.s.bank[O], 18)

    def test_multiple_units(self) -> None:
        set_hand(self.s, 0, wool=8)
        game.apply(self.s, 0, bt({"wool": 8}, {"grain": 2}), self.now)
        self.assertEqual(self.s.players[0].hand[Resource.GRAIN], 2)
        self.assertEqual(self.s.players[0].hand[W], 0)

    def test_bank_ratio_from_settings(self) -> None:
        s = make_state(clock=False, overrides={"economy": {"trade": {"bank_ratio": 5}}})
        set_hand(s, 0, lumber=5)
        self.assertEqual(trade.best_ratio(s, 0, L), (5, "bank"))
        game.apply(s, 0, bt({"lumber": 5}, {"ore": 1}), 0)

    def test_wrong_amounts_rejected(self) -> None:
        set_hand(self.s, 0, lumber=10)
        err = self.reject("trade.bad_ratio", bt({"lumber": 3}, {"ore": 1}))
        self.assertEqual(err.params, {"resource": "lumber", "ratio": 4, "give": 3, "get": 1})
        self.reject("trade.bad_ratio", bt({"lumber": 5}, {"ore": 1}))
        self.reject("trade.bad_ratio", bt({"lumber": 4}, {"ore": 2}))

    def test_cannot_afford(self) -> None:
        set_hand(self.s, 0, lumber=3)
        err = self.reject("trade.cannot_afford", bt({"lumber": 4}, {"ore": 1}))
        self.assertEqual(err.params, {"resource": "lumber", "have": 3, "need": 4})

    def test_bank_lacks_requested_resource(self) -> None:
        set_hand(self.s, 0, lumber=8)
        self.s.bank[O] = 1
        err = self.reject("trade.bank_empty", bt({"lumber": 8}, {"ore": 2}))
        self.assertEqual(err.params, {"resource": "ore", "have": 1, "need": 2})
        game.apply(self.s, 0, bt({"lumber": 4}, {"ore": 1}), self.now)
        self.assertEqual(self.s.bank[O], 0)

    def test_same_resource_rejected(self) -> None:
        set_hand(self.s, 0, lumber=8)
        cmd = BankTrade.model_construct(a="bank_trade", give={L: 4}, get={L: 1})  # bypasses the schema
        self.reject("trade.same_resource", cmd)
        self.reject("command.invalid", bt({"lumber": 4}, {"lumber": 1}))
        self.reject("command.invalid", bt({"lumber": 4, "wool": 4}, {"ore": 2}))

    # ---------------------------------------------------------------- harbors
    def test_generic_harbor_needs_own_building(self) -> None:
        s = self.s
        set_hand(s, 0, wool=6)
        self.reject("trade.bad_ratio", bt({"wool": 3}, {"ore": 1}))
        place(s, 1, GENERIC_V[0])                          # someone else's building
        self.reject("trade.bad_ratio", bt({"wool": 3}, {"ore": 1}))
        s.constructions[1] = Construction(id=1, seat=0, kind=BuildKind.SETTLEMENT, target=GENERIC_V[1],
                                          builder=None, paid={r: 0 for r in Resource}, started_ms=0, done_ms=9999)
        self.reject("trade.bad_ratio", bt({"wool": 3}, {"ore": 1}))   # not finished yet
        del s.constructions[1]
        place(s, 0, GENERIC_V[1], BuildKind.CITY)
        events = game.apply(s, 0, bt({"wool": 6}, {"ore": 2}), self.now)
        self.assertEqual(events[0], Traded(at=self.now, seat=0, give={W: 6}, get={O: 2}, ratio=3, via="harbor"))
        self.assertEqual(trade.owned_harbors(s, 0), [0])
        self.assertEqual(trade.owned_harbors(s, 1), [0])

    def test_specific_harbor_only_for_its_resource(self) -> None:
        s = self.s
        place(s, 0, LUMBER_V[1])
        set_hand(s, 0, lumber=2, ore=4)
        self.assertEqual(trade.best_ratio(s, 0, L), (2, "harbor"))
        self.assertEqual(trade.best_ratio(s, 0, O), (4, "bank"))
        game.apply(s, 0, bt({"lumber": 2}, {"brick": 1}), self.now)
        self.reject("trade.bad_ratio", bt({"ore": 2}, {"brick": 1}))
        game.apply(s, 0, bt({"ore": 4}, {"brick": 1}), self.now)
        self.assertEqual(s.players[0].hand[Resource.BRICK], 2)

    def test_best_ratio_chosen(self) -> None:
        s = self.s
        place(s, 0, GENERIC_V[0])
        place(s, 0, LUMBER_V[0])
        self.assertEqual(trade.best_ratio(s, 0, L), (2, "harbor"))
        self.assertEqual(trade.best_ratio(s, 0, W), (3, "harbor"))
        self.assertEqual(trade.best_ratio(s, 1, L), (4, "bank"))
        set_hand(s, 0, lumber=4)
        self.reject("trade.bad_ratio", bt({"lumber": 4}, {"ore": 1}))   # must use the best ratio
        game.apply(s, 0, bt({"lumber": 4}, {"ore": 2}), self.now)

    def test_harbor_ratios_from_settings_and_switch(self) -> None:
        s = make_state(clock=False, overrides={"board": {"harbors": {"generic_ratio": 4, "specific_ratio": 3}}})
        place(s, 0, GENERIC_V[0])
        place(s, 0, LUMBER_V[0])
        self.assertEqual(trade.best_ratio(s, 0, W), (4, "bank"))       # equal to the bank: via bank
        self.assertEqual(trade.best_ratio(s, 0, L), (3, "harbor"))
        s = make_state(clock=False, overrides={"trading": {"harbor_trade": False}})
        place(s, 0, LUMBER_V[0])
        self.assertEqual(trade.best_ratio(s, 0, L), (4, "bank"))

    # ------------------------------------------------------------------ setup
    def test_setup_restriction(self) -> None:
        s = make_state(clock=False, setup_done=False, overrides={"setup": {"bank_trade_during_setup": False}})
        set_hand(s, 0, lumber=4)
        with self.assertRaises(RuleError) as cm:
            game.apply(s, 0, bt({"lumber": 4}, {"ore": 1}), 0)
        self.assertEqual(cm.exception.code, "trade.setup_forbidden")
        s.players[0].setup_done = True
        game.apply(s, 0, bt({"lumber": 4}, {"ore": 1}), 0)

    def test_setup_trade_allowed_by_default(self) -> None:
        s = make_state(clock=False, setup_done=False)
        set_hand(s, 0, lumber=4)
        game.apply(s, 0, bt({"lumber": 4}, {"ore": 1}), 0)
        self.assertEqual(s.players[0].hand[O], 1)


if __name__ == "__main__":
    unittest.main()
