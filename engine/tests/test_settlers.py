"""Settlers variation (WP23a): buying settlers, gathering, blocking the robber, sight."""
from __future__ import annotations

import unittest
from typing import Any

from engine import game, sight
from engine.errors import RuleError
from engine.events import Hand, SettlerLanded, SettlersGathered
from engine.rules import robber, settlers
from engine.rules.visibility import update_visibility
from engine.settings.enums import BuildKind, Resource
from engine.state import Construction, GameState, SettlerStep
from engine.tests.test_dice import make_state, place, set_hand, totals
from engine.tests.test_devcards import ALL_KNIGHTS

GATHER = {"settlers": {"gather": True}}
BLOCK = {"settlers": {"block_robber": True}}
FULL_COST = dict(lumber=1, wool=1, grain=1, fish=2)
NOW = 100


def staying(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """``overrides`` with settlers staying after setup (unless they say otherwise)."""
    out = dict(overrides or {})
    out["settlers"] = {"leave_after_setup": False, **out.get("settlers", {})}
    return out


def new_state(overrides: dict[str, Any] | None = None, n: int = 3) -> GameState:
    s = make_state(n=n, overrides=staying(overrides), stage=3)
    for p in s.players:
        set_hand(s, p.seat)
    return s


def code(fn, *args, **kw) -> tuple[str, dict]:  # type: ignore[no-untyped-def]
    try:
        fn(*args, **kw)
    except RuleError as exc:
        return exc.code, exc.params
    raise AssertionError("no RuleError")


def buy(s: GameState, seat: int, **fields: Any) -> list:
    return game.apply(s, seat, {"a": "buy_settler", **fields}, NOW)


def land_vertex_with_resources(s: GameState, k: int = 2) -> int:
    """A vertex touching at least ``k`` producing hexes away from the robber."""
    gb = s.board
    return next(v for v in gb.board.land_vertices
                if sum(1 for h in gb.board.vertex_hexes[v] if gb.hex_resource(h) is not None) >= k
                and s.robber_hex not in gb.board.vertex_hexes[v])


def own_settlers(s: GameState, seat: int) -> list[int]:
    return sorted(s.players[seat].settler_ids)


def only_settler(s: GameState, seat: int, vertex: int) -> int:
    """Remove every settler but ``seat``'s first, and put that one on ``vertex``."""
    keep = own_settlers(s, seat)[0]
    for sid in list(s.settlers):
        if sid != keep:
            del s.settlers[sid]
    for p in s.players:
        p.settler_ids = [i for i in p.settler_ids if i == keep]
    s.settlers[keep].vertex = vertex
    return keep


class BuySettlerTest(unittest.TestCase):
    def test_default_cost_includes_fish(self) -> None:
        cost = new_state().settings.economy.costs.settler
        self.assertEqual({r.value: n for r, n in cost.items() if n}, FULL_COST)

    def test_buy_pays_and_lands_at_own_building(self) -> None:
        s = new_state()
        v = land_vertex_with_resources(s)
        place(s, 0, v)
        set_hand(s, 0, **FULL_COST, ore=1)
        before = totals(s)
        count = len(s.players[0].settler_ids)
        ev = buy(s, 0)
        self.assertEqual([type(e) for e in ev][:2], [Hand, SettlerLanded])
        landed = ev[1]
        self.assertEqual((landed.seat, landed.vertex), (0, v))
        self.assertEqual(s.settlers[landed.settler].vertex, v)
        self.assertEqual(len(s.players[0].settler_ids), count + 1)
        self.assertEqual(s.players[0].hand_count, 1)
        self.assertEqual(totals(s), before)

    def test_buy_at_chosen_building(self) -> None:
        s = new_state()
        verts = sorted(s.board.board.land_vertices)
        place(s, 0, verts[0])
        place(s, 0, verts[40], BuildKind.CITY)
        set_hand(s, 0, **FULL_COST)
        ev = buy(s, 0, vertex=verts[40])
        self.assertEqual(ev[1].vertex, verts[40])

    def test_not_available_when_settlers_leave(self) -> None:
        s = new_state({"settlers": {"leave_after_setup": True}})
        place(s, 0, sorted(s.board.board.land_vertices)[0])
        set_hand(s, 0, **FULL_COST)
        self.assertEqual(code(buy, s, 0)[0], "settler.not_available")
        self.assertFalse(settlers.can_buy(s, 0))

    def test_refusals(self) -> None:
        s = new_state()
        verts = sorted(s.board.board.land_vertices)
        s.players[0].setup_done = False
        self.assertEqual(code(buy, s, 0)[0], "settler.setup_not_done")
        s.players[0].setup_done = True
        c, params = code(buy, s, 0)
        self.assertEqual(c, "settler.cannot_afford")
        set_hand(s, 0, **FULL_COST)
        self.assertEqual(code(buy, s, 0)[0], "settler.no_building")
        place(s, 1, verts[5])
        self.assertEqual(code(buy, s, 0, vertex=verts[5]), ("settler.not_your_building", {"vertex": verts[5]}))
        place(s, 0, verts[0])
        maxed = s.settings.settlers.max
        while len(s.players[0].settler_ids) < maxed:
            set_hand(s, 0, **FULL_COST)
            buy(s, 0)
        set_hand(s, 0, **FULL_COST)
        self.assertEqual(code(buy, s, 0), ("settler.max", {"max": maxed}))
        self.assertEqual(s.players[0].hand_count, sum(FULL_COST.values()))


class BotTest(unittest.TestCase):
    def test_bots_buy_settlers_and_gather_in_the_settlers_preset(self) -> None:
        from engine.settings import load_preset
        from engine.sim.bots import make_bot
        from engine.sim.runner import Simulation
        from engine.tests.fixtures import make_seats
        kinds: dict[str, int] = {}

        def count(batch: list) -> None:
            for e in batch:
                kinds[e.k] = kinds.get(e.k, 0) + 1

        settings = load_preset("settlers", players=3)
        sim = Simulation(settings, make_seats(3), 2, [make_bot("greedy", i, 2000 + i) for i in range(3)], on_events=count)
        while not sim.state.finished and len(sim.state.dice_history) < 400:
            sim.step()
        self.assertTrue(sim.state.finished)
        self.assertGreater(kinds.get("settlers_gathered", 0), 0)
        self.assertGreater(max(len(p.settler_ids) for p in sim.state.players), 1)
        self.assertNotIn("settler_left", kinds)


class GatherTest(unittest.TestCase):
    def setup_settler(self, overrides: dict[str, Any] | None = GATHER) -> tuple[GameState, int, int]:
        s = new_state(overrides)
        v = land_vertex_with_resources(s)
        return s, only_settler(s, 0, v), v

    def expected(self, s: GameState, v: int, cards: int = 1) -> dict[Resource, int]:
        out: dict[Resource, int] = {}
        for h in s.board.board.vertex_hexes[v]:
            res = s.board.hex_resource(h)
            if res is not None and h != s.robber_hex:
                out[res] = out.get(res, 0) + cards
        return out

    def test_off_by_default(self) -> None:
        s, _, _ = self.setup_settler(None)
        self.assertEqual(settlers.gather(s, 3, NOW), [])

    def test_numbers_follow_settler_order(self) -> None:
        s = new_state(GATHER)
        place(s, 0, sorted(s.board.board.land_vertices)[0])
        for _ in range(3):
            set_hand(s, 0, **FULL_COST)
            buy(s, 0)
        ids = own_settlers(s, 0)
        self.assertEqual([settlers.gather_numbers(s, i) for i in ids], [[3], [11], [2, 12], [3]])

    def test_first_settler_gathers_on_three(self) -> None:
        s, sid, v = self.setup_settler()
        before = totals(s)
        self.assertEqual(settlers.gather(s, 11, NOW), [])
        ev = settlers.gather(s, 3, NOW)
        gathered = [e for e in ev if isinstance(e, SettlersGathered)]
        self.assertEqual(len(gathered), 1)
        want = self.expected(s, v)
        self.assertEqual(gathered[0].gains, {0: want})
        self.assertEqual(gathered[0].settlers, [sid])
        self.assertEqual({r: n for r, n in s.players[0].hand.items() if n}, want)
        self.assertEqual(totals(s), before)
        self.assertIn(Hand(at=NOW, seat=0, hand=dict(s.players[0].hand)), ev)

    def test_gather_cards_setting(self) -> None:
        s, _, v = self.setup_settler({"settlers": {"gather": True, "gather_cards": 2}})
        ev = settlers.gather(s, 3, NOW)
        self.assertEqual(ev[0].gains, {0: self.expected(s, v, 2)})

    def test_custom_rolls(self) -> None:
        s, _, v = self.setup_settler({"settlers": {"gather": True, "gather_rolls": [[4, 10]]}})
        self.assertEqual(settlers.gather(s, 3, NOW), [])
        self.assertEqual(settlers.gather(s, 10, NOW)[0].gains, {0: self.expected(s, v)})

    def test_robber_hex_gives_nothing(self) -> None:
        s, _, v = self.setup_settler()
        hexes = [h for h in s.board.board.vertex_hexes[v] if s.board.hex_resource(h) is not None]
        s.robber_hex = hexes[0]
        want = self.expected(s, v)
        ev = settlers.gather(s, 3, NOW)
        got = ev[0].gains[0] if ev else {}
        self.assertEqual(got, want)

    def test_walking_or_building_settlers_do_not_gather(self) -> None:
        s, sid, v = self.setup_settler()
        st = s.settlers[sid]
        st.path = [s.board.board.vertex_neighbors[v][0]]
        self.assertEqual(settlers.gather(s, 3, NOW), [])
        st.path = []
        w = s.board.board.vertex_neighbors[v][0]
        st.step = SettlerStep(edge=s.board.board.vertex_edges[v][0], from_v=v, to_v=w, t0=0, t1=10)
        self.assertEqual(settlers.gather(s, 3, NOW), [])
        st.step = None
        cid = s.next_id("construction")
        s.constructions[cid] = Construction(id=cid, seat=0, kind=BuildKind.SETTLEMENT, target=v,
                                            builder=sid, paid={}, started_ms=0, done_ms=10)
        self.assertEqual(settlers.gather(s, 3, NOW), [])
        del s.constructions[cid]
        self.assertTrue(settlers.gather(s, 3, NOW))

    def test_bank_pays_what_it_has(self) -> None:
        s, _, v = self.setup_settler()
        res = next(iter(self.expected(s, v)))
        for p in s.players[1:]:
            p.hand[res] += s.bank[res]
            s.bank[res] = 0
            break
        ev = settlers.gather(s, 3, NOW)
        got = ev[0].gains.get(0, {}) if ev else {}
        self.assertNotIn(res, got)

    def test_dice_roll_triggers_gathering(self) -> None:
        s = make_state(n=3, overrides=staying(GATHER), stage=3, rolls=[[1, 2]])
        for p in s.players:
            set_hand(s, p.seat)
        v = land_vertex_with_resources(s)
        only_settler(s, 0, v)
        ev = game.advance(s, s.settings.clock.roll_interval_ms)
        self.assertTrue(any(isinstance(e, SettlersGathered) for e in ev))

    def test_event_view_hides_gains_like_production(self) -> None:
        s, _, _ = self.setup_settler({"settlers": {"gather": True}, "visibility": {"production_log": "own"}})
        ev = settlers.gather(s, 3, NOW)[0]
        vis = s.settings.visibility
        self.assertEqual(set(ev.public(0, vis)["gains"]), {"0"})
        self.assertEqual(ev.public(1, vis)["gains"], {})


class BlockRobberTest(unittest.TestCase):
    def test_blocked_hexes_off_by_default(self) -> None:
        self.assertEqual(settlers.blocked_hexes(new_state()), frozenset())

    def test_robber_avoids_settler_hexes(self) -> None:
        s = new_state(BLOCK)
        start = s.robber_hex
        free = robber.legal_neighbours(s, start)
        self.assertTrue(free)
        target = free[0]
        sid = own_settlers(s, 0)[0]
        s.settlers[sid].vertex = s.board.board.hex_vertices[target][0]
        self.assertIn(target, settlers.blocked_hexes(s))
        self.assertNotIn(target, robber.legal_neighbours(s, start))

    def test_knight_cannot_go_to_settler_hex(self) -> None:
        from engine.rules import devcards  # noqa: F401  (registers play_dev_card)
        s = new_state({**ALL_KNIGHTS, **BLOCK})
        set_hand(s, 0, wool=1, grain=1, ore=1)
        game.apply(s, 0, {"a": "buy_dev_card"}, NOW)
        s.dice_history.append(8)
        start = s.robber_hex
        h = next(n for n in s.board.board.hex_neighbors[start] if s.board.board.is_land(n))
        sid = own_settlers(s, 1)[0]
        s.settlers[sid].vertex = s.board.board.hex_vertices[h][0]
        self.assertEqual(code(game.apply, s, 0, {"a": "play_dev_card", "card": "knight", "hex": h}, 200),
                         ("dev.blocked_by_settler", {"hex": h}))


class SettlerSightTest(unittest.TestCase):
    def test_settlers_reveal_under_fog(self) -> None:
        s = new_state({"visibility": {"map": "growing"}})
        self.assertTrue(sight.settlers_reveal(s, 0))
        sid = own_settlers(s, 0)[0]
        far = next(v for v in s.board.board.land_vertices
                   if not sight.vertex_seen(s.board, sight.seen_hexes(s, 0), v))
        s.settlers[sid].vertex = far
        update_visibility(s, NOW)
        self.assertTrue(set(s.board.board.vertex_hexes[far]) <= sight.seen_hexes(s, 0))

    def test_open_map_does_not_track(self) -> None:
        self.assertFalse(sight.settlers_reveal(new_state(), 0))


if __name__ == "__main__":
    unittest.main()
