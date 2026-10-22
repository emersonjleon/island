"""Settler movement rules (WP5): landing, move_settler, stepping, interrupts, codec."""
import json
import unittest
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from engine import codec, game
from engine.board import walkgraph
from engine.commands import MoveSettler
from engine.errors import RuleError
from engine.events import Event, Points, SettlerArrived, SettlerLanded, SettlerPath, SettlerStepEvent
from engine.rng import Rng
from engine.rules import movement
from engine.settings import STAGE_LATER, parse_settings
from engine.state import GameState
from engine.tests.fixtures import make_seats, make_settings, standard_board
from engine.tests.test_walkgraph import bfs_hops, generated, two_islands

MS = 1500


@contextmanager
def movement_only(departures: list[tuple[int, int, int]] | None = None) -> Iterator[None]:
    """Registry with only the movement handlers plus a recording departure listener
    that returns a marker ``Points(seat=-1, points=vertex)`` event."""
    with game.temporary_registry(empty=True):
        game.on_new_game(order=movement.LANDING_ORDER)(movement.land_settlers)
        game.command_handler("move_settler")(movement.move_settler)
        game.timer_handler(game.TIMER_SETTLER_ARRIVE)(movement.settler_arrive)
        if departures is not None:
            @game.connect(game.SIG_SETTLER_DEPARTING)
            def _listener(state: GameState, now_ms: int, *, settler: int, vertex: int) -> list[Event]:
                departures.append((now_ms, settler, vertex))
                return [Points(at=now_ms, seat=-1, points=vertex)]
        yield


def kinds(events: list[Event]) -> list[str]:
    return [e.k for e in events]


def vertex_at(state: GameState, start: int, hops: int) -> int:
    """Smallest vertex id exactly ``hops`` walk edges from ``start``."""
    dist = bfs_hops(state.board.board, start)
    return min(v for v, d in dist.items() if d == hops)


class MovementBase(unittest.TestCase):
    overrides: dict[str, Any] | None = None

    def setUp(self) -> None:
        self.departures: list[tuple[int, int, int]] = []
        self._stack = ExitStack()
        self._stack.enter_context(movement_only(self.departures))
        game.set_check_rejects(True)
        self._stack.callback(game.set_check_rejects, False)
        self.state, self.events = game.new_game(make_settings(self.overrides), make_seats(3), 1,
                                                board=standard_board())

    def tearDown(self) -> None:
        self._stack.close()

    def move(self, settler: int, to: int, now: int, mode: str = "replace", seat: int | None = None) -> list[Event]:
        st = self.state
        out = game.advance(st, now)
        out += game.apply(st, st.settlers[settler].seat if seat is None else seat,
                          MoveSettler(settler=settler, to_vertex=to, mode=mode), now)
        return out


class LandingTest(unittest.TestCase):
    def new(self, n: int, seed: int, settings=None, board=None) -> tuple[GameState, list[Event]]:
        with movement_only():
            return game.new_game(settings or make_settings(), make_seats(n), seed,
                                 board=board if board is not None else standard_board())

    def test_landing_events_and_state(self) -> None:
        for n in (2, 3, 4):
            state, events = self.new(n, 5)
            self.assertEqual([type(e) for e in events], [SettlerLanded] * n)
            b = state.board.board
            for k, ev in enumerate(events):
                self.assertEqual((ev.at, ev.settler, ev.seat), (0, k + 1, k))
                s = state.settlers[ev.settler]
                self.assertEqual((s.seat, s.vertex, s.path, s.step, s.timer_id), (k, ev.vertex, [], None, None))
                self.assertIn(s.vertex, b.coastal_vertices)
                self.assertEqual(state.players[k].settler_ids, [ev.settler])
                self.assertEqual(movement.settler_at_rest(state, ev.settler), ev.vertex)
            _, game_seed = game.derive_seeds(5)
            self.assertEqual([e.vertex for e in events], walkgraph.landing_points(b, n, Rng(game_seed)))
            self.assertEqual(len(state.timers), 0)

    def test_even_spread_and_deterministic(self) -> None:
        cycle = walkgraph.landing_cycle(standard_board().board)
        offsets = set()
        for seed in range(30):
            state, events = self.new(4, seed)
            idx = [cycle.index(e.vertex) for e in events]
            self.assertEqual([(idx[(i + 1) % 4] - idx[i]) % 30 for i in range(4)], [7, 8, 7, 8])
            offsets.add(idx[0])
            again, events2 = self.new(4, seed)
            self.assertEqual(events, events2)
            self.assertEqual(codec.state_hash(state), codec.state_hash(again))
        self.assertGreater(len(offsets), 5)

    def test_generated_boards(self) -> None:
        for land in (7, 19, 37, 61):
            settings = parse_settings({"board": {"land_hexes": land}})
            for seed in range(4):
                state, events = self.new(4, seed, settings=settings, board=generated(land, seed))
                b = state.board.board
                vs = [e.vertex for e in events]
                self.assertEqual(len(set(vs)), 4)
                for v in vs:
                    self.assertIn(v, b.coastal_vertices)
        # without a fixed board (generator inside new_game)
        with movement_only():
            st, ev = game.new_game(make_settings(), make_seats(3), 9)
        self.assertEqual(len(ev), 3)

    def test_several_settlers_per_player(self) -> None:
        settings = parse_settings({"settlers": {"start_count": 2}}, implemented_stage=STAGE_LATER)
        state, events = self.new(3, 2, settings=settings)
        self.assertEqual([e.seat for e in events], [0, 1, 2, 0, 1, 2])
        self.assertEqual([e.settler for e in events], [1, 2, 3, 4, 5, 6])
        self.assertEqual(state.players[0].settler_ids, [1, 4])
        self.assertEqual(state.players[2].settler_ids, [3, 6])
        cycle = walkgraph.landing_cycle(state.board.board)
        idx = [cycle.index(e.vertex) for e in events]
        self.assertEqual(sorted((idx[(i + 1) % 6] - idx[i]) % 30 for i in range(6)), [5] * 6)


class WalkTest(MovementBase):
    def test_walk_timing_exact(self) -> None:
        st = self.state
        s = st.settlers[1]
        start = s.vertex
        target = vertex_at(st, start, 4)
        path = walkgraph.shortest_path(st, 0, start, target)
        ev = self.move(1, target, 100)
        self.assertEqual(kinds(ev), ["points", "settler_step", "settler_path"])
        step = ev[1]
        self.assertEqual((step.settler, step.from_v, step.to_v, step.t0, step.t1), (1, start, path[0], 100, 100 + MS))
        self.assertEqual(step.edge, walkgraph.edge_between(st.board.board, start, path[0]))
        self.assertEqual(ev[2].path, path[1:])
        self.assertEqual(s.path, path[1:])
        self.assertIsNone(movement.settler_at_rest(st, 1))
        self.assertEqual(st.timers.get(s.timer_id).due_ms, 100 + MS)
        # nothing fires 1 ms early
        self.assertEqual(game.advance(st, 99 + MS), [])
        ev = game.advance(st, 100 + MS)
        self.assertEqual(kinds(ev), ["settler_arrived", "points", "settler_step"])
        self.assertEqual((ev[0].at, ev[0].vertex), (100 + MS, path[0]))
        self.assertEqual((ev[2].t0, ev[2].t1), (100 + MS, 100 + 2 * MS))
        # jump far ahead: remaining steps fire at their logical times
        ev = game.advance(st, 100_000)
        arrivals = [e for e in ev if isinstance(e, SettlerArrived)]
        self.assertEqual([(e.at, e.vertex) for e in arrivals],
                         [(100 + (i + 2) * MS, path[i + 1]) for i in range(3)])
        self.assertEqual(movement.settler_at_rest(st, 1), target)
        self.assertEqual((s.vertex, s.step, s.path, s.timer_id), (target, None, [], None))
        self.assertEqual(len(st.timers), 0)
        self.assertEqual([d[2] for d in self.departures], [start] + path[:-1])
        self.assertEqual([d[0] for d in self.departures], [100 + i * MS for i in range(4)])

    def test_move_to_own_vertex(self) -> None:
        v = self.state.settlers[2].vertex
        ev = self.move(2, v, 0)
        self.assertEqual(ev, [SettlerPath(at=0, settler=2, path=[])])
        self.assertEqual(self.departures, [])
        self.assertEqual(len(self.state.timers), 0)

    def test_settlers_walk_independently(self) -> None:
        st = self.state
        a, b = st.settlers[1], st.settlers[2]
        self.move(1, b.vertex, 0)           # walk to (and through) another player's settler
        self.move(2, a.vertex, 0)
        game.advance(st, 100_000)
        hops = bfs_hops(st.board.board, b.vertex)[a.vertex]
        self.assertEqual(len(self.departures), 2 * hops)
        self.assertNotEqual(a.vertex, b.vertex)


class RoadSpeedTest(MovementBase):
    overrides = {"settlers": {"ms_per_edge": MS, "road_speed_pct": 200}}

    def test_own_road_is_faster(self) -> None:
        st = self.state
        s = st.settlers[1]
        start = s.vertex
        target = vertex_at(st, start, 3)
        path = walkgraph.shortest_path(st, 0, start, target)
        b = st.board.board
        e1 = walkgraph.edge_between(b, start, path[0])
        e2 = walkgraph.edge_between(b, path[0], path[1])
        e3 = walkgraph.edge_between(b, path[1], path[2])
        st.roads[e1] = 0
        st.roads[e2] = 1                    # opponent's road: normal speed
        ev = self.move(1, target, 0)
        self.assertEqual(ev[1].t1, MS // 2)
        st.roads[e3] = 0                    # finished mid-walk: speeds up the later edge
        ev = game.advance(st, 100_000)
        steps = [e for e in ev if isinstance(e, SettlerStepEvent)]
        self.assertEqual([(e.edge, e.t0, e.t1) for e in steps],
                         [(e2, 750, 2250), (e3, 2250, 3000)])
        self.assertEqual(s.vertex, target)


class InterruptTest(MovementBase):
    def setUp(self) -> None:
        super().setUp()
        st = self.state
        self.s = st.settlers[1]
        self.start = self.s.vertex
        self.target = vertex_at(st, self.start, 4)
        self.path = walkgraph.shortest_path(st, 0, self.start, self.target)
        self.move(1, self.target, 0)

    def test_replace_mid_edge_finishes_edge(self) -> None:
        st, s = self.state, self.s
        timer_id, step = s.timer_id, s.step
        other = vertex_at(st, self.start, 2)
        ev = self.move(1, other, 700)
        expected = walkgraph.shortest_path(st, 0, self.path[0], other)
        self.assertEqual(ev, [SettlerPath(at=700, settler=1, path=expected)])
        self.assertEqual((s.timer_id, s.step), (timer_id, step))     # current edge untouched
        self.assertEqual(len(self.departures), 1)
        ev = game.advance(st, 100_000)
        self.assertEqual(ev[0], SettlerArrived(at=MS, settler=1, vertex=self.path[0]))
        arrivals = [e.vertex for e in ev if isinstance(e, SettlerArrived)]
        self.assertEqual(arrivals, [self.path[0]] + expected)
        self.assertEqual(s.vertex, other)
        self.assertEqual(len(self.departures), 1 + len(expected))
        self.assertEqual(st.now_ms, 100_000)

    def test_replace_to_edge_end_stops_there(self) -> None:
        st, s = self.state, self.s
        ev = self.move(1, self.path[0], 10)
        self.assertEqual(ev, [SettlerPath(at=10, settler=1, path=[])])
        ev = game.advance(st, 100_000)
        self.assertEqual(ev, [SettlerArrived(at=MS, settler=1, vertex=self.path[0])])
        self.assertEqual(movement.settler_at_rest(st, 1), self.path[0])

    def test_replace_back_to_start(self) -> None:
        st, s = self.state, self.s
        ev = self.move(1, self.start, 10)
        self.assertEqual(ev[-1].path, [self.start])
        game.advance(st, 100_000)
        self.assertEqual(s.vertex, self.start)
        self.assertEqual([d[2] for d in self.departures], [self.start, self.path[0]])

    def test_append_extends_queue(self) -> None:
        st, s = self.state, self.s
        extra_target = vertex_at(st, self.target, 2)
        extra = walkgraph.shortest_path(st, 0, self.target, extra_target)
        ev = self.move(1, extra_target, 200, mode="append")
        self.assertEqual(ev, [SettlerPath(at=200, settler=1, path=self.path[1:] + extra)])
        ev = game.advance(st, 100_000)
        arrivals = [(e.at, e.vertex) for e in ev if isinstance(e, SettlerArrived)]
        full = self.path + extra
        self.assertEqual(arrivals, [((i + 1) * MS, v) for i, v in enumerate(full)])
        self.assertEqual(movement.settler_at_rest(st, 1), extra_target)

    def test_append_on_last_edge_and_at_rest(self) -> None:
        st, s = self.state, self.s
        game.advance(st, 3 * MS + 5)            # walking the last edge, queue empty
        self.assertEqual(s.path, [])
        nxt = vertex_at(st, self.target, 1)
        ev = self.move(1, nxt, 3 * MS + 5, mode="append")
        self.assertEqual(ev, [SettlerPath(at=3 * MS + 5, settler=1, path=[nxt])])
        game.advance(st, 5 * MS)
        self.assertEqual(movement.settler_at_rest(st, 1), nxt)
        # append at rest behaves like replace: starts walking at once
        back = self.target
        ev = self.move(1, back, 5 * MS, mode="append")
        self.assertEqual(kinds(ev), ["points", "settler_step", "settler_path"])
        self.assertEqual(ev[1].to_v, back)


class RejectTest(MovementBase):
    def reject(self, code: str, seat: int, settler: int, to: int, params: dict | None = None) -> None:
        before = codec.state_hash(self.state)
        with self.assertRaises(RuleError) as cm:
            game.apply(self.state, seat, MoveSettler(settler=settler, to_vertex=to), self.state.now_ms)
        self.assertEqual(cm.exception.code, code)
        if params is not None:
            self.assertEqual(cm.exception.params, params)
        self.assertEqual(codec.state_hash(self.state), before)

    def test_codes(self) -> None:
        b = self.state.board.board
        land = b.land_vertices[0]
        sea_v = next(v for v in range(len(b.vertices)) if not b.land_vertex(v))
        self.reject("movement.unknown_settler", 0, 99, land, {"settler": 99})
        self.reject("movement.not_your_settler", 1, 1, land, {"settler": 1})
        self.reject("movement.unknown_vertex", 0, 1, len(b.vertices), {"vertex": len(b.vertices)})
        self.reject("movement.not_land", 0, 1, sea_v, {"vertex": sea_v})
        self.assertEqual(self.departures, [])

    def test_rejects_while_walking(self) -> None:
        st = self.state
        self.move(1, vertex_at(st, st.settlers[1].vertex, 3), 0)
        game.advance(st, 400)
        sea_v = next(v for v in range(len(st.board.board.vertices)) if not st.board.board.land_vertex(v))
        self.reject("movement.not_land", 0, 1, sea_v)
        self.reject("movement.not_your_settler", 2, 1, st.board.board.land_vertices[0])

    def test_unreachable(self) -> None:
        with movement_only():
            st, ev = game.new_game(make_settings(), make_seats(2), 3, board=two_islands())
            b = st.board.board
            here = st.settlers[1].vertex
            island = 0 if here in b.hex_vertices[0] else 1
            far = b.hex_vertices[1 - island][0]
            self.state = st
            self.reject("movement.unreachable", 0, 1, far, {"settler": 1, "from": here, "to": far})


class DepartureAndStaleTimerTest(MovementBase):
    def test_departing_once_per_vertex(self) -> None:
        st = self.state
        s = st.settlers[3]
        t1 = vertex_at(st, s.vertex, 3)
        ev = self.move(3, t1, 0)
        ev += self.move(3, vertex_at(st, t1, 2), 2000)            # replace mid-edge
        ev += self.move(3, s.vertex if s.step is None else s.step.to_v, 2100, mode="append")
        ev += game.advance(st, 100_000)
        steps = [e for e in ev if isinstance(e, SettlerStepEvent)]
        arrivals = [e for e in ev if isinstance(e, SettlerArrived)]
        self.assertGreater(len(steps), 3)
        self.assertEqual(len(self.departures), len(steps))
        self.assertEqual(len(arrivals), len(steps))
        self.assertEqual(len({(d[0], d[2]) for d in self.departures}), len(self.departures))
        # each marker immediately precedes its step event
        for i, e in enumerate(ev):
            if isinstance(e, SettlerStepEvent):
                self.assertEqual(ev[i - 1], Points(at=e.t0, seat=-1, points=e.from_v))

    def test_deleted_settler_timer_ignored(self) -> None:
        st = self.state
        self.move(1, vertex_at(st, st.settlers[1].vertex, 3), 0)
        self.assertEqual(len(st.timers), 1)
        del st.settlers[1]
        st.players[0].settler_ids.remove(1)
        self.assertEqual(game.advance(st, 100_000), [])
        self.assertEqual(len(st.timers), 0)

    def test_stale_timer_ignored(self) -> None:
        st = self.state
        s = st.settlers[1]
        self.move(1, vertex_at(st, s.vertex, 2), 0)
        st.timers.schedule(10, game.TIMER_SETTLER_ARRIVE, {"settler": 1})   # not s.timer_id
        self.assertEqual(game.advance(st, 10), [])
        self.assertIsNotNone(s.step)

    def test_listener_removing_settler(self) -> None:
        with game.temporary_registry():
            @game.connect(game.SIG_SETTLER_DEPARTING, order=200)
            def _remove(state: GameState, now_ms: int, *, settler: int, vertex: int) -> list[Event]:
                state.settlers.pop(settler, None)
                return []
            ev = self.move(2, vertex_at(self.state, self.state.settlers[2].vertex, 2), 0)
        self.assertEqual(kinds(ev), ["points", "settler_path"])
        self.assertEqual(len(self.state.timers), 0)


class CodecTest(unittest.TestCase):
    SCRIPT = [  # (now, settler, target hops from its current spot, mode)
        (0, 1, 5, "replace"), (300, 2, 3, "replace"), (2200, 1, 2, "replace"),
        (2500, 2, 2, "append"), (4000, 3, 4, "replace"), (5100, 1, 3, "append"),
    ]

    def run_game(self, split_at: int | None) -> tuple[list[dict], str]:
        with movement_only([]):
            st, events = game.new_game(make_settings(), make_seats(3), 21, board=standard_board())
            st.roads[st.board.board.land_edges[10]] = 0
            out = [e.to_dict() for e in events]
            for now, sid, hops, mode in self.SCRIPT:
                if split_at is not None and now >= split_at:
                    out += [e.to_dict() for e in game.advance(st, split_at)]
                    st = codec.load(json.loads(json.dumps(codec.dump(st))))
                    split_at = None
                s = st.settlers[sid]
                out += [e.to_dict() for e in game.advance(st, now)]
                origin = s.path[-1] if mode == "append" and s.path else (s.step.to_v if s.step else s.vertex)
                target = vertex_at(st, origin, hops)
                out += [e.to_dict() for e in
                        game.apply(st, s.seat, MoveSettler(settler=sid, to_vertex=target, mode=mode), now)]
            out += [e.to_dict() for e in game.advance(st, 60_000)]
            return out, codec.state_hash(st)

    def test_round_trip_mid_walk(self) -> None:
        ref_events, ref_hash = self.run_game(None)
        self.assertGreater(len(ref_events), 20)
        for split in (700, 2200, 3001, 4500, 5100):
            events, h = self.run_game(split)
            self.assertEqual(events, ref_events, split)
            self.assertEqual(h, ref_hash, split)


class RegistrationTest(unittest.TestCase):
    def test_handlers_registered(self) -> None:
        reg = game._REG
        self.assertIs(reg.commands["move_settler"], movement.move_settler)
        self.assertIs(reg.timers[game.TIMER_SETTLER_ARRIVE], movement.settler_arrive)
        self.assertIn((movement.LANDING_ORDER, movement.land_settlers),
                      [(o, fn) for o, _, fn in reg.new_game])

    def test_full_registry_new_game_lands_settlers(self) -> None:
        state, events = game.new_game(make_settings(), make_seats(3), 1, board=standard_board())
        landed = [e for e in events if isinstance(e, SettlerLanded)]
        self.assertEqual(len(landed), 3)
        self.assertEqual(sorted(state.settlers), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
