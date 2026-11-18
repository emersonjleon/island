"""A seven rolled while a building is under construction never touches it: the
cost is already in escrow (``Construction.paid``), out of the robber's reach, and
the building completes on time. Regression for "the robber stole while my
settlement was being built and it never appeared"."""
from __future__ import annotations

import unittest

from engine import game
from engine.events import Built, ConstructionCancelled, RobberStole
from engine.rules import placement, robber
from engine.settings.enums import Resource
from engine.state import Building
from engine.tests.test_placement import R, S, WP6Case, act, bcmd, give, new_state, setup_player, totals

ALL_IN = {"robber": {"steal_pct": 100, "card_limit": 0, "spare_setup": False}}


class RobberDuringConstructionTest(WP6Case):
    def _network_settlement(self, seed: int):
        state, _ = new_state(2, ALL_IN, seed=seed)
        now = setup_player(state, 0, 0)
        give(state, 0, {r: 6 for r in (Resource.BRICK, Resource.LUMBER, Resource.WOOL, Resource.GRAIN)})
        targets = []
        for e in placement.legal_targets(state, 0, R):
            act(state, 0, bcmd(R, e), now)
            now += state.settings.build.time_ms.road
            game.advance(state, now)
            targets = placement.legal_targets(state, 0, S)
            if targets:
                break
        self.assertTrue(targets, "no settlement spot reachable in two roads")
        act(state, 0, bcmd(S, targets[0]), now)
        (c,) = state.constructions.values()
        return state, c, targets[0], now

    def test_seven_mid_build_keeps_escrow_and_building_completes(self) -> None:
        for seed in range(1, 8):
            state, c, v, now = self._network_settlement(seed)
            paid = dict(c.paid)
            before = totals(state)
            events = robber.on_seven(state, now + 1000)
            stole = [e for e in events if isinstance(e, RobberStole) and e.seat == 0]
            self.assertTrue(stole, "the test hand should have been robbed")
            self.assertEqual(sum(state.player(0).hand.values()), 0)
            self.assertIn(c.id, state.constructions)
            self.assertEqual(state.constructions[c.id].paid, paid)
            self.assertEqual(totals(state), before)
            done = game.advance(state, c.done_ms)
            self.assertFalse([e for e in done if isinstance(e, ConstructionCancelled)])
            self.assertTrue([e for e in done if isinstance(e, Built) and e.target == v])
            self.assertEqual(state.buildings[v], Building(0, S))


if __name__ == "__main__":
    unittest.main()
