"""WP6 timed construction: escrow, completion time, cancel/refund, builder leaving,
first-to-finish conflicts, conservation and codec round trips."""
from __future__ import annotations

import unittest

from engine import codec, game
from engine.errors import RuleError
from engine.events import Built, ConstructionCancelled, ConstructionStarted
from engine.rng import Rng
from engine.rules import placement
from engine.settings.enums import Resource
from engine.state import Building, GameState
from engine.tests.test_placement import (
    C, R, S, WP6Case, act, add_settler, bcmd, brute_buildable, give, inner_vertices, kinds, new_state,
    piece_totals, setup_player, teleport, totals,
)

SETTLEMENT_COST = {Resource.BRICK: 1, Resource.LUMBER: 1, Resource.WOOL: 1, Resource.GRAIN: 1}


def cancelled(events: list) -> list[ConstructionCancelled]:
    return [e for e in events if isinstance(e, ConstructionCancelled)]


class StartTest(WP6Case):
    def test_escrow_piece_and_timer(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        sid = add_settler(state, 0, v)
        hand_before = dict(state.player(0).hand)
        before = totals(state)
        events = act(state, 0, bcmd(S, v), 500)
        (c,) = state.constructions.values()
        self.assertEqual((c.seat, c.kind, c.target, c.builder, c.setup), (0, S, v, sid, True))
        self.assertEqual((c.started_ms, c.done_ms), (500, 8500))
        self.assertEqual({r: n for r, n in c.paid.items() if n}, SETTLEMENT_COST)
        for r in Resource:
            self.assertEqual(state.player(0).hand[r], hand_before[r] - SETTLEMENT_COST.get(r, 0))
        self.assertEqual(state.player(0).pieces_left[S], 4)
        self.assertEqual(totals(state), before)
        t = state.timers.get(c.timer_id)
        self.assertEqual((t.due_ms, t.kind, t.payload), (8500, game.TIMER_CONSTRUCTION_DONE, {"construction": c.id}))
        started = events[0]
        self.assertIsInstance(started, ConstructionStarted)
        self.assertEqual((started.t0, started.t1, started.builder), (500, 8500, sid))
        self.assertEqual(kinds(events)[:2], ["construction_started", "hand"])

    def test_completes_exactly_at_build_time(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 1234)
        self.assertEqual(game.next_wakeup(state), 1234 + 8000)
        game.advance(state, 1234 + 7999)
        self.assertNotIn(v, state.buildings)
        events = game.advance(state, 1234 + 8000)
        self.assertEqual(state.buildings[v], Building(0, S))
        built = next(e for e in events if isinstance(e, Built))
        self.assertEqual((built.at, built.seat, built.kind, built.target), (9234, 0, S, v))
        self.assertEqual(state.constructions, {})

    def test_untimed_network_builds_complete_immediately(self) -> None:
        state, _ = new_state(2, {"build": {"network_builds_timed": False}})
        now = setup_player(state, 0, 0)
        give(state, 0, {Resource.BRICK: 1, Resource.LUMBER: 1})
        e = placement.legal_targets(state, 0, R)[0]
        events = act(state, 0, bcmd(R, e), now)
        self.assertEqual(state.roads[e], 0)
        self.assertEqual(state.constructions, {})
        self.assertEqual(kinds(events)[:3], ["construction_started", "hand", "built"])
        # setup builds stay timed
        state2, _ = new_state(2, {"build": {"network_builds_timed": False}})
        v = inner_vertices(state2)[0]
        add_settler(state2, 0, v)
        act(state2, 0, bcmd(S, v), 0)
        self.assertNotIn(v, state2.buildings)


class CancelTest(WP6Case):
    def test_cancel_full_refund_returns_piece(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        hand0, bank0 = dict(state.player(0).hand), dict(state.bank)
        act(state, 0, bcmd(S, v), 0)
        cid = next(iter(state.constructions))
        tid = state.constructions[cid].timer_id
        events = act(state, 0, {"a": "cancel_build", "construction": cid}, 100)
        self.assertEqual(state.player(0).hand, hand0)
        self.assertEqual(state.bank, bank0)
        self.assertEqual(state.player(0).pieces_left[S], 5)
        self.assertIsNone(state.timers.get(tid))
        (ev,) = cancelled(events)
        self.assertEqual((ev.id, ev.seat, ev.reason), (cid, 0, "cancelled"))
        self.assertEqual({r: n for r, n in ev.refund.items() if n}, SETTLEMENT_COST)
        game.advance(state, 20_000)
        self.assertNotIn(v, state.buildings)

    def test_partial_refund_floors_per_resource(self) -> None:
        state, _ = new_state(2, {"build": {"refund_pct": 50},
                                 "economy": {"costs": {"settlement": {"brick": 3, "lumber": 1}},
                                             "starting_materials": {"brick": 4, "lumber": 4}}})
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        before = totals(state)
        bank_brick = state.bank[Resource.BRICK]
        act(state, 0, bcmd(S, v), 0)
        events = act(state, 0, {"a": "cancel_build", "construction": 1}, 10)
        (ev,) = cancelled(events)
        self.assertEqual(ev.refund[Resource.BRICK], 1)
        self.assertEqual(ev.refund[Resource.LUMBER], 0)
        self.assertEqual(state.player(0).hand[Resource.BRICK], 2)
        self.assertEqual(state.player(0).hand[Resource.LUMBER], 3)
        self.assertEqual(state.bank[Resource.BRICK], bank_brick + 2)
        self.assertEqual(totals(state), before)

    def test_cancel_errors(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 0)
        self.assertRejects("build.unknown_construction", state, 0, {"a": "cancel_build", "construction": 99}, 0)
        self.assertRejects("build.not_your_construction", state, 1, {"a": "cancel_build", "construction": 1}, 0)

    def test_builder_departing_cancels(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        sid = add_settler(state, 0, v)
        other = add_settler(state, 0, inner_vertices(state)[-1])
        hand0 = dict(state.player(0).hand)
        act(state, 0, bcmd(S, v), 0)
        self.assertEqual(teleport(state, other, v, 100), [])     # another settler leaving: no effect
        events = game.emit(state, game.SIG_SETTLER_DEPARTING, 200, settler=sid, vertex=v)
        (ev,) = cancelled(events)
        self.assertEqual((ev.reason, ev.seat), ("builder_left", 0))
        self.assertEqual(state.constructions, {})
        self.assertEqual(state.player(0).hand, hand0)
        self.assertEqual(state.player(0).pieces_left[S], 5)
        self.assertEqual(game.next_wakeup(state), None)


class ConflictTest(WP6Case):
    def race(self, v0: int, v1: int, t0: int, t1: int) -> tuple[GameState, list]:
        state, _ = new_state(2)
        add_settler(state, 0, v0)
        add_settler(state, 1, v1)
        hand1 = dict(state.player(1).hand)
        first, second = ((0, v0, t0), (1, v1, t1)) if t0 <= t1 else ((1, v1, t1), (0, v0, t0))
        act(state, first[0], bcmd(S, first[1]), first[2])
        act(state, second[0], bcmd(S, second[1]), second[2])
        events = game.advance(state, max(t0, t1) + 8000)
        self.hand1 = hand1
        return state, events

    def test_same_vertex_first_to_finish_wins(self) -> None:
        v = inner_vertices(self.race_state())[0]
        state, events = self.race(v, v, 0, 1000)
        self.assertEqual(state.buildings, {v: Building(0, S)})
        (ev,) = cancelled(events)
        self.assertEqual((ev.seat, ev.reason), (1, "conflict"))
        self.assertEqual(state.player(1).hand, self.hand1)
        self.assertEqual(state.player(1).pieces_left[S], 5)
        self.assertEqual(state.player(1).setup_remaining[S], 2)
        self.assertEqual(state.constructions, {})
        # the loser was cancelled at the winner's finish time, before its own
        self.assertEqual(ev.at, 8000)

    def test_later_start_finishing_first_wins(self) -> None:
        st = self.race_state()
        v = inner_vertices(st)[0]
        n = st.board.board.vertex_neighbors[v][0]
        state, events = self.race(v, n, 1000, 0)   # seat 1 started first on the neighbour
        self.assertEqual(state.buildings, {n: Building(1, S)})
        (ev,) = cancelled(events)
        self.assertEqual((ev.seat, ev.reason, ev.at), (0, "conflict", 8000))

    def test_neighbouring_vertex(self) -> None:
        st = self.race_state()
        v = inner_vertices(st)[0]
        n = st.board.board.vertex_neighbors[v][0]
        state, events = self.race(v, n, 0, 500)
        self.assertEqual(state.buildings, {v: Building(0, S)})
        (ev,) = cancelled(events)
        self.assertEqual(ev.seat, 1)

    def test_equal_finish_time_resolves_by_timer_order(self) -> None:
        st = self.race_state()
        v = inner_vertices(st)[0]
        for order in ((0, 1), (1, 0)):
            with self.subTest(order=order):
                state, _ = new_state(2)
                add_settler(state, 0, v)
                add_settler(state, 1, v)
                for seat in order:
                    act(state, seat, bcmd(S, v), 300)
                events = game.advance(state, 8300)
                self.assertEqual(state.buildings, {v: Building(order[0], S)})
                (ev,) = cancelled(events)
                self.assertEqual(ev.seat, order[1])

    def test_far_constructions_unaffected(self) -> None:
        st = self.race_state()
        v, w = inner_vertices(st)[0], inner_vertices(st)[-1]
        state, events = self.race(v, w, 0, 0)
        self.assertEqual(state.buildings, {v: Building(0, S), w: Building(1, S)})
        self.assertEqual(cancelled(events), [])

    def test_network_road_race(self) -> None:
        state, _ = new_state(2)
        now = setup_player(state, 0, 0)
        now = setup_player(state, 1, now)
        b = state.board.board
        # a free edge both players can reach: give each a road touching it
        state.roads.clear()
        state.buildings.clear()
        x = inner_vertices(state)[0]
        e0, e1, target = b.vertex_edges[x][:3]
        state.roads[e0], state.roads[e1] = 0, 1
        give(state, 0, {Resource.BRICK: 1, Resource.LUMBER: 1})
        give(state, 1, {Resource.BRICK: 1, Resource.LUMBER: 1})
        act(state, 1, bcmd(R, target), now)
        act(state, 0, bcmd(R, target), now)
        events = game.advance(state, now + 3000)
        self.assertEqual(state.roads[target], 1)
        (ev,) = cancelled(events)
        self.assertEqual((ev.seat, ev.reason), (0, "conflict"))

    def test_settlement_blocks_road_through_vertex(self) -> None:
        state, _ = new_state(2)
        now = setup_player(state, 0, 0)
        now = setup_player(state, 1, now)
        b = state.board.board
        state.roads.clear()
        state.buildings.clear()
        x = inner_vertices(state)[0]
        e_own, e_new, e_opp = b.vertex_edges[x][:3]
        state.roads[e_own], state.roads[e_opp] = 0, 1
        give(state, 0, {Resource.BRICK: 1, Resource.LUMBER: 1})
        give(state, 1, SETTLEMENT_COST)
        act(state, 1, bcmd(S, x), now)                # settlement on x, done at now + 8000
        act(state, 0, bcmd(R, e_new), now + 6000)     # road continuing via x, done at now + 9000
        events = game.advance(state, now + 9000)
        self.assertEqual(state.buildings[x], Building(1, S))
        self.assertNotIn(e_new, state.roads)
        (ev,) = cancelled(events)
        self.assertEqual((ev.seat, ev.reason, ev.at), (0, "conflict", now + 8000))

    def race_state(self) -> GameState:
        return new_state(2)[0]


class ConservationTest(WP6Case):
    """Random builds, cancels, settler moves and time steps keep resources and pieces."""

    def run_seed(self, seed: int, steps: int) -> None:
        state, _ = new_state(3, seed=seed)
        rng = Rng(seed)
        b = state.board.board
        land_v = list(b.land_vertices)
        for seat in range(3):
            add_settler(state, seat, rng.choice(inner_vertices(state)))
        total0 = totals(state)
        pieces0 = {seat: piece_totals(state, seat) for seat in range(3)}
        now = 0
        for step in range(steps):
            seat = rng.randbelow(3)
            op = rng.randbelow(10)
            try:
                if op < 5:
                    p = state.player(seat)
                    if p.settler_ids and rng.randbelow(2):
                        target_v = rng.choice(land_v)
                        teleport(state, p.settler_ids[0], target_v, now)
                    kind = rng.choice([S, R, C])
                    legal = placement.legal_targets(state, seat, kind)
                    if legal and rng.randbelow(4):
                        target = rng.choice(legal)
                    else:
                        target = rng.randbelow(len(b.edges) if kind is R else len(b.vertices))
                    if p.settler_ids and not p.setup_done:
                        if kind is not R and target in land_v:
                            teleport(state, p.settler_ids[0], target, now)
                        elif kind is R and p.last_setup_settlement is not None:
                            teleport(state, p.settler_ids[0], p.last_setup_settlement, now)
                    act(state, seat, bcmd(kind, target), now)
                elif op < 6 and state.constructions and rng.randbelow(2):
                    cid = rng.choice(sorted(state.constructions))
                    act(state, rng.choice([seat, state.constructions[cid].seat]),
                        {"a": "cancel_build", "construction": cid}, now)
                elif op < 8:
                    give(state, seat, {rng.choice(list(Resource)): rng.randint(1, 3)})
                else:
                    now += rng.randint(0, 6000)
                    game.advance(state, now)
            except RuleError:
                pass
            self.assertEqual(totals(state), total0, f"seed {seed} step {step}")
            for s in range(3):
                self.assertEqual(piece_totals(state, s), pieces0[s], f"seed {seed} step {step}")
                for r in Resource:
                    self.assertGreaterEqual(state.player(s).hand[r], 0)
            for r in Resource:
                self.assertGreaterEqual(state.bank[r], 0)
            if step % 25 == 0:
                for s in range(3):
                    self.assertEqual(placement.buildable(state, s), brute_buildable(state, s))
        self.built_any = self.built_any or bool(state.buildings)

    def test_many_seeds(self) -> None:
        self.built_any = False
        for seed in range(12):
            with self.subTest(seed=seed):
                self.run_seed(seed, 300)
        self.assertTrue(self.built_any)


class CodecTest(WP6Case):
    def test_round_trip_mid_construction(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        n = state.board.board.vertex_neighbors[v][0]
        add_settler(state, 0, v)
        add_settler(state, 1, n)
        act(state, 0, bcmd(S, v), 100)
        act(state, 1, bcmd(S, n), 2000)
        game.advance(state, 5000)
        clone = codec.load(codec.dump(state))
        self.assertEqual(codec.state_hash(clone), codec.state_hash(state))
        ev_a = game.advance(state, 30_000)
        ev_b = game.advance(clone, 30_000)
        self.assertEqual([e.to_dict() for e in ev_a], [e.to_dict() for e in ev_b])
        self.assertEqual(codec.state_hash(clone), codec.state_hash(state))
        self.assertEqual(state.buildings, {v: Building(0, S)})
        self.assertIn("construction_cancelled", kinds(ev_a))


class RegistryTest(unittest.TestCase):
    def test_production_registry_has_wp6_handlers(self) -> None:
        from engine.rules import construction
        reg = game._REG
        self.assertIs(reg.commands["build"], construction.handle_build)
        self.assertIs(reg.commands["cancel_build"], construction.handle_cancel_build)
        self.assertIs(reg.timers[game.TIMER_CONSTRUCTION_DONE], construction.construction_done)


if __name__ == "__main__":
    unittest.main()
