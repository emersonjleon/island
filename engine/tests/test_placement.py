"""WP6 placement rules: distance rule, builder settler, setup roads, network building,
pieces, costs and ``buildable`` events.

The module-level helpers (no TestCase classes) are shared with ``test_construction``
and ``test_setup``. Tests run in an isolated registry holding only the WP6 handlers
plus a dummy dice handler, and create settlers directly in the state, so they do not
depend on WP5's landing hook or WP7's dice.
"""
from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest import mock

from engine import game
from engine.errors import RuleError
from engine.events import Buildable, Event
from engine.rules import construction, movement, placement, setup
from engine.scheduler import Timer
from engine.settings.enums import BuildKind, Resource
from engine.settings.loading import parse_settings
from engine.state import Building, GameState, Settler, SettlerStep
from engine.tests.fixtures import make_seats, standard_board

S, R, C = BuildKind.SETTLEMENT, BuildKind.ROAD, BuildKind.CITY


# ============================================================== shared helpers
def _fallback_at_rest(state: GameState, settler_id: int) -> int | None:
    s = state.settlers.get(settler_id)
    if s is None or s.step is not None or s.path:
        return None
    return s.vertex


def _dummy_dice(state: GameState, timer: Timer, now_ms: int) -> list[Event]:
    state.ext.setdefault("dice_fired", []).append(now_ms)
    return []


@contextmanager
def wp6_registry() -> Iterator[None]:
    """Registry with only the WP6 handlers (registered in production order) and a
    dummy dice handler."""
    with ExitStack() as stack:
        stack.enter_context(game.temporary_registry(empty=True))
        if not hasattr(movement, "settler_at_rest"):
            stack.enter_context(mock.patch.object(movement, "settler_at_rest", _fallback_at_rest, create=True))
        game.on_new_game(setup.STARTING_MATERIALS_ORDER)(setup.give_starting_materials)
        game.connect(game.SIG_BUILT)(setup.on_built)
        game.after_step(placement.BUILDABLE_ORDER)(placement.update_buildable)
        game.command_handler("build")(construction.handle_build)
        game.command_handler("cancel_build")(construction.handle_cancel_build)
        game.connect(game.SIG_SETTLER_DEPARTING)(construction.on_settler_departing)
        game.timer_handler(game.TIMER_CONSTRUCTION_DONE)(construction.construction_done)
        game.timer_handler(game.TIMER_DICE_ROLL)(_dummy_dice)
        yield


class WP6Case(unittest.TestCase):
    def setUp(self) -> None:
        self._stack = ExitStack()
        self._stack.enter_context(wp6_registry())
        game.set_check_rejects(True)
        self._stack.callback(game.set_check_rejects, False)

    def tearDown(self) -> None:
        self._stack.close()

    def assertRejects(self, code: str, state: GameState, seat: int, cmd: dict[str, Any], now: int) -> RuleError:
        game.advance(state, now)
        with self.assertRaises(RuleError) as cm:
            game.apply(state, seat, cmd, now)
        self.assertEqual(cm.exception.code, code, cm.exception)
        return cm.exception


def new_state(n: int = 3, overrides: dict[str, Any] | None = None, stage: int | None = None,
              seed: int = 1) -> tuple[GameState, list[Event]]:
    settings = parse_settings(overrides or {}, implemented_stage=stage)
    return game.new_game(settings, make_seats(n), seed=seed, board=standard_board())


def add_settler(state: GameState, seat: int, vertex: int) -> int:
    sid = state.next_id("settler")
    state.settlers[sid] = Settler(id=sid, seat=seat, vertex=vertex)
    state.player(seat).settler_ids.append(sid)
    return sid


def teleport(state: GameState, sid: int, vertex: int, now: int) -> list[Event]:
    """Stand-in for movement: announce the departure, then place the settler at rest."""
    s = state.settlers[sid]
    events = game.emit(state, game.SIG_SETTLER_DEPARTING, now, settler=sid, vertex=s.vertex)
    s.vertex, s.step, s.path = vertex, None, []
    return events


def act(state: GameState, seat: int, cmd: dict[str, Any], now: int) -> list[Event]:
    events = game.advance(state, now)
    return events + game.apply(state, seat, cmd, now)


def bcmd(kind: BuildKind, target: int, settler: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"a": "build", "kind": kind.value}
    d["edge" if kind is R else "vertex"] = target
    if settler is not None:
        d["settler"] = settler
    return d


def inner_vertices(state: GameState) -> list[int]:
    b = state.board.board
    return [v for v in b.land_vertices if all(b.is_land(h) for h in b.vertex_hexes[v]) and len(b.vertex_hexes[v]) == 3]


def own_settler(state: GameState, seat: int, vertex: int) -> int:
    p = state.player(seat)
    if p.settler_ids:
        return p.settler_ids[0]
    return add_settler(state, seat, vertex)


def setup_player(state: GameState, seat: int, now: int, spots: list[int] | None = None) -> int:
    """Run ``seat``'s whole setup (settlement then road, repeated) with a settler
    teleported between spots; returns the time afterwards."""
    ts = state.settings.build.time_ms
    p = state.player(seat)
    spots = list(spots or [])
    while not p.setup_done:
        roads_done = state.settings.setup.roads - p.setup_remaining[R]
        if p.setup_remaining[S] > 0 and (p.setup_remaining[R] == 0 or roads_done >= p.setup_settlements_built):
            v = spots.pop(0) if spots else next(x for x in inner_vertices(state)
                                                if x in placement.legal_targets(state, seat, S))
            sid = own_settler(state, seat, v)
            teleport(state, sid, v, now)
            act(state, seat, bcmd(S, v), now)
            now += ts.settlement
        else:
            last = p.last_setup_settlement
            assert last is not None
            e = next(e for e in placement.legal_targets(state, seat, R) if last in state.board.board.edge_vertices[e])
            sid = own_settler(state, seat, last)
            teleport(state, sid, last, now)
            act(state, seat, bcmd(R, e), now)
            now += ts.road
        game.advance(state, now)
    return now


def give(state: GameState, seat: int, res: dict[Resource, int]) -> None:
    """Move cards from the bank to a hand (keeps the conservation total)."""
    for r, n in res.items():
        n = min(n, state.bank[r])
        state.bank[r] -= n
        state.player(seat).hand[r] += n


def totals(state: GameState) -> dict[Resource, int]:
    out = dict(state.bank)
    for p in state.players:
        for r in Resource:
            out[r] += p.hand[r]
    for c in state.constructions.values():
        for r in Resource:
            out[r] += c.paid[r]
    return out


def piece_totals(state: GameState, seat: int) -> dict[BuildKind, int]:
    p = state.player(seat)
    out = dict(p.pieces_left)
    for c in state.constructions.values():
        if c.seat == seat:
            out[c.kind] += 1
    out[R] += sum(1 for s in state.roads.values() if s == seat)
    for b in state.buildings.values():
        if b.seat == seat:
            out[b.kind] += 1
    return out


def brute_buildable(state: GameState, seat: int) -> dict[str, list[int]]:
    b = state.board.board
    rng_v, rng_e = range(len(b.vertices)), range(len(b.edges))
    if state.phase == "finished":
        return {"roads": [], "settlements": [], "cities": [], "megacities": []}
    return {
        "roads": [e for e in rng_e if placement.build_error(state, seat, R, e) is None],
        "settlements": [v for v in rng_v if placement.build_error(state, seat, S, v) is None],
        "cities": [v for v in rng_v if placement.build_error(state, seat, C, v) is None],
        "megacities": [v for v in rng_v if placement.build_error(state, seat, BuildKind.MEGACITY, v) is None],
    }


def kinds(events: list[Event]) -> list[str]:
    return [e.k for e in events]


# ======================================================================= tests
class TargetValidityTest(WP6Case):
    def test_not_land_and_unknown_ids(self) -> None:
        state, _ = new_state(2)
        b = state.board.board
        sea_v = next(v for v in range(len(b.vertices)) if not b.land_vertex(v))
        sea_e = next(e for e in range(len(b.edges)) if not b.land_edge(e))
        add_settler(state, 0, sea_v)
        self.assertRejects("build.not_land", state, 0, bcmd(S, sea_v), 0)
        self.assertRejects("build.not_land", state, 0, bcmd(S, 10_000), 0)
        self.assertRejects("build.not_land", state, 0, bcmd(R, sea_e), 0)
        self.assertRejects("build.not_land", state, 0, bcmd(R, 10_000), 0)


class DistanceRuleTest(WP6Case):
    def test_distance_rule_and_occupied(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        n = state.board.board.vertex_neighbors[v][0]
        add_settler(state, 0, v)
        sid1 = add_settler(state, 1, n)
        act(state, 0, bcmd(S, v), 0)
        game.advance(state, 8000)
        self.assertEqual(state.buildings[v], Building(0, S))
        err = self.assertRejects("build.distance_rule", state, 1, bcmd(S, n), 8000)
        self.assertEqual(err.params, {"kind": "settlement", "target": n})
        teleport(state, sid1, v, 8000)
        self.assertRejects("build.occupied", state, 1, bcmd(S, v), 8000)
        legal = placement.legal_targets(state, 1, S)
        self.assertNotIn(v, legal)
        for x in state.board.board.vertex_neighbors[v]:
            self.assertNotIn(x, legal)

    def test_distance_rule_pure(self) -> None:
        state, _ = new_state(2)
        b = state.board.board
        v = inner_vertices(state)[0]
        state.buildings[v] = Building(1, S)
        for n in b.vertex_neighbors[v]:
            self.assertEqual(placement.settlement_error(state, 0, n, "setup").code, "build.distance_rule")
        two_away = next(x for n in b.vertex_neighbors[v] for x in b.vertex_neighbors[n]
                        if x != v and x not in b.vertex_neighbors[v])
        self.assertIsNone(placement.settlement_error(state, 0, two_away, "setup"))


class BuilderTest(WP6Case):
    def test_setup_settlement_needs_own_settler_at_rest(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        n = state.board.board.vertex_neighbors[v][0]
        self.assertRejects("build.need_settler", state, 0, bcmd(S, v), 0)
        other = add_settler(state, 1, v)
        self.assertRejects("build.need_settler", state, 0, bcmd(S, v), 0)
        self.assertRejects("build.not_your_settler", state, 0, bcmd(S, v, settler=other), 0)
        self.assertRejects("build.not_your_settler", state, 0, bcmd(S, v, settler=999), 0)
        own = add_settler(state, 0, n)
        self.assertRejects("build.need_settler", state, 0, bcmd(S, v), 0)
        self.assertRejects("build.need_settler", state, 0, bcmd(S, v, settler=own), 0)
        # walking towards v (mid-edge) or with a queued path: not at rest
        s = state.settlers[own]
        e = state.board.board.vertex_edges[n][0]
        s.step = SettlerStep(edge=e, from_v=n, to_v=v, t0=0, t1=1500)
        self.assertRejects("build.need_settler", state, 0, bcmd(S, v), 0)
        s.step, s.vertex, s.path = None, v, [n]
        self.assertRejects("build.need_settler", state, 0, bcmd(S, v), 0)
        s.path = []
        events = act(state, 0, bcmd(S, v), 0)
        (c,) = state.constructions.values()
        self.assertEqual((c.builder, c.setup, c.kind, c.target), (own, True, S, v))
        self.assertEqual(kinds(events)[:2], ["construction_started", "hand"])

    def test_settler_busy(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        sid = add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 0)
        game.advance(state, 8000)
        e1, e2 = state.board.board.vertex_edges[v][:2]
        act(state, 0, bcmd(R, e1), 8000)
        self.assertRejects("build.settler_busy", state, 0, bcmd(R, e2), 8000)
        self.assertRejects("build.settler_busy", state, 0, bcmd(R, e2, settler=sid), 8000)
        add_settler(state, 0, v)                       # a second, idle settler may build
        act(state, 0, bcmd(R, e2), 8000)
        self.assertEqual(sorted(c.builder for c in state.constructions.values()), [1, 2])

    def test_network_builds_need_no_builder(self) -> None:
        state, _ = new_state(2)
        now = setup_player(state, 0, 0)
        self.assertEqual(state.player(0).settler_ids, [])
        give(state, 0, {Resource.BRICK: 2, Resource.LUMBER: 2})
        e = placement.legal_targets(state, 0, R)[0]
        act(state, 0, bcmd(R, e), now)
        (c,) = state.constructions.values()
        self.assertEqual((c.builder, c.setup), (None, False))


class SetupRoadTest(WP6Case):
    def test_road_must_touch_finished_setup_settlement(self) -> None:
        state, _ = new_state(2)
        b = state.board.board
        v = inner_vertices(state)[0]
        e = b.vertex_edges[v][0]
        add_settler(state, 0, v)
        self.assertRejects("build.road_needs_settlement", state, 0, bcmd(R, e), 0)
        act(state, 0, bcmd(S, v), 0)
        self.assertRejects("build.road_needs_settlement", state, 0, bcmd(R, e), 100)  # still building
        game.advance(state, 8000)
        far = next(x for x in b.land_edges if v not in b.edge_vertices[x])
        self.assertRejects("build.road_needs_settlement", state, 0, bcmd(R, far), 8000)
        act(state, 0, bcmd(R, e), 8000)
        game.advance(state, 11000)
        self.assertEqual(state.roads, {e: 0})
        self.assertEqual(state.player(0).setup_remaining, {S: 1, R: 1})

    def test_road_touches_newest_settlement_only(self) -> None:
        for flag in (True, False):
            with self.subTest(road_touches_new_settlement=flag):
                state, _ = new_state(2, {"setup": {"road_touches_new_settlement": flag}})
                v1, v2 = inner_vertices(state)[0], inner_vertices(state)[-1]
                sid = add_settler(state, 0, v1)
                act(state, 0, bcmd(S, v1), 0)
                game.advance(state, 8000)
                teleport(state, sid, v2, 8000)
                act(state, 0, bcmd(S, v2), 8000)
                game.advance(state, 16000)
                teleport(state, sid, v1, 16000)
                e1 = state.board.board.vertex_edges[v1][0]
                if flag:
                    self.assertRejects("build.road_needs_settlement", state, 0, bcmd(R, e1), 16000)
                else:
                    act(state, 0, bcmd(R, e1), 16000)

    def test_road_next_to_opponent_settlement_is_not_enough(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        add_settler(state, 1, v)
        act(state, 1, bcmd(S, v), 0)
        game.advance(state, 8000)
        add_settler(state, 0, v)
        self.assertRejects("build.road_needs_settlement", state, 0, bcmd(R, state.board.board.vertex_edges[v][0]), 8000)


class SetupModeTest(WP6Case):
    def test_network_building_forbidden_during_own_setup(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 0)
        game.advance(state, 8000)
        give(state, 0, {Resource.GRAIN: 2, Resource.ORE: 3})
        self.assertRejects("build.setup_unfinished", state, 0, bcmd(C, v), 8000)
        # both setup settlements done, roads left: a third settlement is a network build
        p = state.player(0)
        p.setup_remaining[S] = 0
        far = next(x for x in inner_vertices(state) if x in placement.legal_targets(state, 1, S))
        self.assertRejects("build.setup_unfinished", state, 0, bcmd(S, far), 8000)

    def test_setup_limit_counts_pending_builds(self) -> None:
        state, _ = new_state(2, {"setup": {"settlements": 1, "roads": 1}})
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 0)
        far = inner_vertices(state)[-1]
        add_settler(state, 0, far)
        self.assertRejects("build.setup_limit", state, 0, bcmd(S, far), 0)
        self.assertEqual(placement.legal_targets(state, 0, S), [])

    def test_network_build_during_setup_flag(self) -> None:
        state, _ = new_state(2, {"setup": {"network_build_during_setup": True}})
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 0)
        game.advance(state, 8000)
        give(state, 0, {Resource.GRAIN: 2, Resource.ORE: 3})
        act(state, 0, bcmd(C, v), 8000)
        (c,) = state.constructions.values()
        self.assertEqual((c.kind, c.setup, c.builder), (C, False, None))

    def test_already_building(self) -> None:
        state, _ = new_state(2)
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        add_settler(state, 0, v)
        act(state, 0, bcmd(S, v), 0)
        self.assertRejects("build.already_building", state, 0, bcmd(S, v), 0)


class NetworkTest(WP6Case):
    def setUp(self) -> None:
        super().setUp()
        self.state, _ = new_state(2)
        self.now = setup_player(self.state, 0, 0)
        self.now = setup_player(self.state, 1, self.now)
        self.assertTrue(self.state.player(0).setup_done and self.state.player(1).setup_done)

    def test_road_connectivity(self) -> None:
        st, b = self.state, self.state.board.board
        give(st, 0, {Resource.BRICK: 5, Resource.LUMBER: 5})
        legal = placement.legal_targets(st, 0, R)
        self.assertTrue(legal)
        for e in legal:
            self.assertTrue(placement.road_connected(st, 0, e))
        lonely = next(e for e in b.land_edges if e not in st.roads and not placement.road_connected(st, 0, e))
        self.assertRejects("build.not_connected", st, 0, bcmd(R, lonely), self.now)
        e = legal[0]
        act(st, 0, bcmd(R, e), self.now)
        self.assertRejects("build.already_building", st, 0, bcmd(R, e), self.now)
        game.advance(st, self.now + 3000)
        self.assertEqual(st.roads[e], 0)
        self.assertRejects("build.occupied", st, 0, bcmd(R, e), self.now + 3000)

    def test_road_not_through_opponent_building(self) -> None:
        st, b = self.state, self.state.board.board
        st.roads.clear()
        st.buildings.clear()
        x = inner_vertices(st)[0]
        e_in, e_out = b.vertex_edges[x][:2]
        st.roads[e_in] = 0
        self.assertTrue(placement.road_connected(st, 0, e_out))
        st.buildings[x] = Building(1, S)
        self.assertFalse(placement.road_connected(st, 0, e_out))
        self.assertEqual(placement.road_error(st, 0, e_out, "network").code, "build.not_connected")
        st.buildings[x] = Building(0, S)
        self.assertTrue(placement.road_connected(st, 0, e_out))

    def test_settlement_needs_own_road(self) -> None:
        st, b = self.state, self.state.board.board
        give(st, 0, {r: 3 for r in Resource})
        cands = [v for v in b.land_vertices if placement.settlement_error(st, 0, v, "setup") is None]
        unconnected = next(v for v in cands if not any(st.roads.get(e) == 0 for e in b.vertex_edges[v]))
        self.assertRejects("build.not_connected", st, 0, bcmd(S, unconnected), self.now)
        for v in placement.legal_targets(st, 0, S):
            self.assertTrue(any(st.roads.get(e) == 0 for e in b.vertex_edges[v]))

    def test_city_upgrade(self) -> None:
        st = self.state
        own = sorted(v for v, bl in st.buildings.items() if bl.seat == 0)
        opp = sorted(v for v, bl in st.buildings.items() if bl.seat == 1)
        give(st, 0, {Resource.GRAIN: 4, Resource.ORE: 6})
        self.assertEqual(placement.legal_targets(st, 0, C), own)
        self.assertRejects("build.not_own_settlement", st, 0, bcmd(C, opp[0]), self.now)
        empty = next(v for v in st.board.board.land_vertices if v not in st.buildings)
        self.assertRejects("build.not_own_settlement", st, 0, bcmd(C, empty), self.now)
        settlements_left = st.player(0).pieces_left[S]
        act(st, 0, bcmd(C, own[0]), self.now)
        self.assertEqual(st.player(0).pieces_left[C], 3)
        game.advance(st, self.now + 10_000)
        self.assertEqual(st.buildings[own[0]], Building(0, C))
        self.assertEqual(st.player(0).pieces_left[S], settlements_left + 1)
        self.assertRejects("build.not_own_settlement", st, 0, bcmd(C, own[0]), self.now + 10_000)

    def test_piece_limits_and_cost(self) -> None:
        st = self.state
        p = st.player(0)
        for r in Resource:
            st.bank[r] += p.hand[r]
            p.hand[r] = 0
        e = placement.legal_targets(st, 0, R)  # empty: cannot afford
        self.assertEqual(e, [])
        cand = next(x for x in st.board.board.land_edges if placement.road_error(st, 0, x, "network") is None)
        err = self.assertRejects("build.cannot_afford", st, 0, bcmd(R, cand), self.now)
        self.assertEqual(err.params["missing"], {"lumber": 1, "brick": 1})
        give(st, 0, {Resource.BRICK: 1, Resource.LUMBER: 1})
        p.pieces_left[R] = 0
        self.assertRejects("build.no_piece", st, 0, bcmd(R, cand), self.now)
        self.assertEqual(placement.legal_targets(st, 0, R), [])
        p.pieces_left[R] = 1
        act(st, 0, bcmd(R, cand), self.now)
        self.assertEqual(p.pieces_left[R], 0)


class BuildableEventsTest(WP6Case):
    def test_sent_only_when_changed(self) -> None:
        state, events = new_state(3)
        initial = [e for e in events if isinstance(e, Buildable)]
        self.assertEqual([e.seat for e in initial], [0, 1, 2])
        for e in initial:
            self.assertEqual({"roads": e.roads, "settlements": e.settlements, "cities": e.cities,
                              "megacities": e.megacities},
                             state.buildable_cache[e.seat])
        self.assertEqual(placement.update_buildable(state, 0), [])
        v = inner_vertices(state)[0]
        add_settler(state, 0, v)
        ev = act(state, 0, bcmd(S, v), 0)
        self.assertEqual([e.seat for e in ev if isinstance(e, Buildable)], [0])   # others unaffected
        self.assertNotIn(v, state.buildable_cache[0]["settlements"])
        self.assertIn(v, state.buildable_cache[1]["settlements"])
        self.assertEqual(game.advance(state, 7999), [])
        ev = game.advance(state, 8000)
        self.assertEqual([e.seat for e in ev if isinstance(e, Buildable)], [0, 1, 2])
        self.assertNotIn(v, state.buildable_cache[1]["settlements"])
        self.assertEqual(placement.update_buildable(state, 8000), [])
        for seat in range(3):
            self.assertEqual(placement.buildable(state, seat), brute_buildable(state, seat))

    def test_view_provider(self) -> None:
        from engine import views
        state, _ = new_state(2)
        views.register_buildable_provider(placement.buildable_view)
        self.assertEqual(views.project_state(state, 1)["buildable"], placement.buildable(state, 1))


if __name__ == "__main__":
    unittest.main()
