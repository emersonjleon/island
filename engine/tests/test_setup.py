"""WP6 setup: starting materials, starting resources (fishing, bank limit), setup
completion with settlers leaving, and the one-time clock start."""
from __future__ import annotations

import unittest

from engine import game
from engine.events import (
    Built, ClockStarted, Hand, SettlerLeft, SetupComplete, StartingMaterials, StartingResources,
)
from engine.rules import setup
from engine.settings.enums import Resource
from engine.state import SettlerStep
from engine.tests.test_placement import (
    R, S, WP6Case, act, add_settler, bcmd, inner_vertices, kinds, new_state, setup_player, teleport, totals,
)

FISH_VERTEX = 16          # standard board: lumber hex 0 + fishing ground 19 (+ plain sea)


def starting_materials(state) -> dict[Resource, int]:
    return {r: state.settings.economy.starting_materials.get(r, 0) for r in Resource}


class StartingMaterialsTest(WP6Case):
    def test_from_bank(self) -> None:
        state, events = new_state(3)
        mats = starting_materials(state)
        for p in state.players:
            self.assertEqual(p.hand, mats)
        for r in Resource:
            self.assertEqual(state.bank[r], 19 - 3 * mats[r])
        sm = [e for e in events if isinstance(e, StartingMaterials)]
        self.assertEqual([e.seat for e in sm], [0, 1, 2])
        self.assertEqual(sm[0].materials, mats)
        self.assertEqual(kinds(events)[:2], ["starting_materials", "hand"])

    def test_not_from_bank(self) -> None:
        state, _ = new_state(2, {"economy": {"starting_materials_from_bank": False}})
        self.assertEqual(state.bank, {r: 19 for r in Resource})
        self.assertEqual(state.player(1).hand, starting_materials(state))


class StartingResourcesTest(WP6Case):
    def build_settlement(self, state, seat: int, v: int, now: int) -> list:
        p = state.player(seat)
        sid = p.settler_ids[0] if p.settler_ids else add_settler(state, seat, v)
        teleport(state, sid, v, now)
        act(state, seat, bcmd(S, v), now)
        return game.advance(state, now + 8000)

    def test_each_of_first_two_settlements_including_fishing(self) -> None:
        state, _ = new_state(2)
        board = state.board
        inner = inner_vertices(state)[0]
        before = dict(state.player(0).hand)
        ev1 = self.build_settlement(state, 0, inner, 0)
        expect1 = {r: 0 for r in Resource}
        for h in board.board.vertex_hexes[inner]:
            r = board.hex_resource(h)
            if r is not None:
                expect1[r] += 1
        (sr1,) = [e for e in ev1 if isinstance(e, StartingResources)]
        self.assertEqual(sr1.gained, expect1)
        ev2 = self.build_settlement(state, 0, FISH_VERTEX, 8000)
        (sr2,) = [e for e in ev2 if isinstance(e, StartingResources)]
        self.assertEqual({r: n for r, n in sr2.gained.items() if n}, {Resource.LUMBER: 1, Resource.FISH: 1})
        cost = state.settings.economy.costs.settlement
        for r in Resource:
            self.assertEqual(state.player(0).hand[r],
                             before[r] - 2 * cost.get(r, 0) + expect1[r] + sr2.gained[r])

    def test_options(self) -> None:
        state, _ = new_state(2, {"economy": {"starting_resources": {"include_fishing": False, "cards_per_hex": 2,
                                                                    "granting_settlements": 1}}})
        ev = self.build_settlement(state, 0, FISH_VERTEX, 0)
        (sr,) = [e for e in ev if isinstance(e, StartingResources)]
        self.assertEqual({r: n for r, n in sr.gained.items() if n}, {Resource.LUMBER: 2})
        ev = self.build_settlement(state, 0, inner_vertices(state)[-1], 8000)
        self.assertEqual([e for e in ev if isinstance(e, StartingResources)], [])

    def test_limited_by_bank(self) -> None:
        state, _ = new_state(2, {"economy": {"starting_resources": {"cards_per_hex": 2}}})
        lumber = state.bank[Resource.LUMBER]
        state.bank[Resource.LUMBER] = 0
        state.player(1).hand[Resource.LUMBER] += lumber       # keep the total constant
        total = totals(state)
        ev = self.build_settlement(state, 0, FISH_VERTEX, 0)
        (sr,) = [e for e in ev if isinstance(e, StartingResources)]
        # the bank only holds the lumber paid for the settlement itself (escrow -> bank on completion)
        self.assertEqual({r: n for r, n in sr.gained.items() if n}, {Resource.LUMBER: 1, Resource.FISH: 2})
        self.assertEqual(state.bank[Resource.LUMBER], 0)
        self.assertEqual(totals(state), total)

    def test_desert_gives_nothing(self) -> None:
        state, _ = new_state(2)
        b = state.board.board
        desert_v = b.hex_vertices[9][0]
        owed = setup.starting_resources_for(state, desert_v)
        for h in b.vertex_hexes[desert_v]:
            r = state.board.hex_resource(h)
            if r is not None:
                owed[r] -= 1
        self.assertEqual(owed, {r: 0 for r in Resource})


class CompletionTest(WP6Case):
    def test_setup_complete_and_settlers_leave(self) -> None:
        state, _ = new_state(2)
        v1, v2 = inner_vertices(state)[0], inner_vertices(state)[-1]
        sid = add_settler(state, 0, v1)
        walker = add_settler(state, 0, v2)
        e = state.board.board.vertex_edges[v2][0]
        to_v = state.board.board.edge_vertices[e][1] if state.board.board.edge_vertices[e][0] == v2 \
            else state.board.board.edge_vertices[e][0]
        state.settlers[walker].step = SettlerStep(edge=e, from_v=v2, to_v=to_v, t0=0, t1=10**8)
        walk_timer = state.timers.schedule(10**8, game.TIMER_SETTLER_ARRIVE, {"settler": walker})
        state.settlers[walker].timer_id = walk_timer
        now = setup_player(state, 0, 0, spots=[v1, v2])
        p = state.player(0)
        self.assertTrue(p.setup_done)
        self.assertEqual(p.setup_remaining, {S: 0, R: 0})
        self.assertEqual(p.setup_settlements_built, 2)
        self.assertEqual(p.last_setup_settlement, v2)
        self.assertEqual(p.settler_ids, [])
        self.assertNotIn(sid, state.settlers)
        self.assertNotIn(walker, state.settlers)
        self.assertIsNone(state.timers.get(walk_timer))
        self.assertFalse(state.player(1).setup_done)
        self.assertEqual(now, 22000)

    def test_completion_event_order(self) -> None:
        state, _ = new_state(2, {"setup": {"settlements": 1, "roads": 0}})
        v = inner_vertices(state)[0]
        sid = add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 0)
        events = game.advance(state, 8000)
        self.assertEqual(kinds(events)[:6], ["built", "starting_resources", "hand", "clock_started",
                                             "setup_complete", "settler_left"])
        self.assertIsInstance(events[0], Built)
        left = next(e for e in events if isinstance(e, SettlerLeft))
        self.assertEqual((left.settler, left.seat), (sid, 0))
        self.assertTrue(any(isinstance(e, SetupComplete) and e.seat == 0 for e in events))

    def test_settlers_stay_when_configured(self) -> None:
        state, _ = new_state(2, {"settlers": {"leave_after_setup": False}}, stage=3)
        sid = add_settler(state, 0, inner_vertices(state)[0])
        setup_player(state, 0, 0)
        self.assertTrue(state.player(0).setup_done)
        self.assertEqual(state.player(0).settler_ids, [sid])
        self.assertIn(sid, state.settlers)


class ClockStartTest(WP6Case):
    def test_first_settlement_starts_clock_once(self) -> None:
        state, _ = new_state(2)
        self.assertFalse(state.clock_started)
        self.assertEqual(state.phase, "setup")
        v, w = inner_vertices(state)[0], inner_vertices(state)[-1]
        add_settler(state, 0, v)
        add_settler(state, 1, w)
        act(state, 0, bcmd(S, v), 1000)
        act(state, 1, bcmd(S, w), 1500)
        self.assertFalse(state.clock_started)
        ev = game.advance(state, 9000)
        (cs,) = [e for e in ev if isinstance(e, ClockStarted)]
        interval = state.settings.clock.roll_interval_ms
        self.assertEqual((cs.at, cs.next_roll_at), (9000, 9000 + interval))
        self.assertTrue(state.clock_started)
        self.assertEqual(state.phase, "running")
        self.assertEqual(state.next_roll_at, 9000 + interval)
        t = state.timers.get(state.roll_timer_id)
        self.assertEqual((t.kind, t.due_ms), (game.TIMER_DICE_ROLL, 9000 + interval))
        ev = game.advance(state, 9500)          # second settlement: no new clock
        self.assertEqual([e for e in ev if isinstance(e, ClockStarted)], [])
        self.assertEqual(len(state.timers.pending(game.TIMER_DICE_ROLL)), 1)
        game.advance(state, 9000 + interval)
        self.assertEqual(state.ext["dice_fired"], [9000 + interval])

    def test_start_clock_is_idempotent(self) -> None:
        state, _ = new_state(2)
        self.assertEqual(setup.start_clock(state, 0)[0].next_roll_at, state.settings.clock.roll_interval_ms)
        self.assertEqual(setup.start_clock(state, 5), [])

    def test_hand_events_private(self) -> None:
        state, events = new_state(2)
        hands = [e for e in events if isinstance(e, Hand)]
        self.assertEqual([h.seat for h in hands], [0, 1])


class RealRegistryTest(unittest.TestCase):
    def test_wp6_hooks_registered(self) -> None:
        from engine.rules import construction, placement
        reg = game._REG
        new_game_fns = [fn for _, _, fn in reg.new_game]
        self.assertIn(setup.give_starting_materials, new_game_fns)
        self.assertIn(placement.update_buildable, [fn for _, _, fn in reg.after_step])
        self.assertIn(setup.on_built, [fn for _, _, fn in reg.signals[game.SIG_BUILT]])
        self.assertIn(construction.on_settler_departing,
                      [fn for _, _, fn in reg.signals[game.SIG_SETTLER_DEPARTING]])


if __name__ == "__main__":
    unittest.main()
