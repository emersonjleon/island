"""Walk graph, path costs, pathfinding and landing points (WP5)."""
import unittest
from collections import deque

from engine.board import walkgraph
from engine.board.generator import generate_board
from engine.board.model import GeneratedBoard
from engine.board.topology import Board, sea_around
from engine.errors import EngineError
from engine.rng import Rng
from engine.settings import load_preset
from engine.settings.enums import Terrain
from engine.state import GameState
from engine.tests.fixtures import make_seats, make_settings, standard_board

SIZES = (7, 10, 19, 37, 61, 100)


def generated(land: int, seed: int) -> GeneratedBoard:
    return generate_board(load_preset("classic", {"board": {"land_hexes": land}}), Rng(seed))


def bare_state(board: GeneratedBoard | None = None, overrides: dict | None = None, n: int = 3) -> GameState:
    """A state without running any rule hook (only walkgraph needs settings, board, roads)."""
    from engine.state import PlayerState
    gb = board or standard_board()
    return GameState(settings=make_settings(overrides), board=gb, rng=Rng(1), seed=1,
                     players=[PlayerState(seat=s.seat, info=s) for s in make_seats(n)], bank={})


def bfs_hops(board: Board, a: int) -> dict[int, int]:
    """Independent reference: hop distances over land edges."""
    dist = {a: 0}
    q = deque([a])
    while q:
        v = q.popleft()
        for e, n in zip(board.vertex_edges[v], board.vertex_neighbors[v]):
            if board.land_edge(e) and n not in dist:
                dist[n] = dist[v] + 1
                q.append(n)
    return dist


def two_islands() -> GeneratedBoard:
    land = [(0, 0), (4, 0)]
    board = Board(land, sea_around(land, 1))
    terrain = tuple(Terrain.FOREST if i < 2 else None for i in range(len(board.hexes)))
    return GeneratedBoard(board=board, terrain=terrain, token=(None,) * len(board.hexes),
                          fishing=frozenset(), harbors=(), robber_start=None)


class WalkGraphTest(unittest.TestCase):
    def test_nodes_and_edges(self) -> None:
        for gb in [standard_board()] + [generated(n, 3) for n in SIZES]:
            b = gb.board
            adj = walkgraph.walk_edges(b)
            nodes = {v for v in range(len(b.vertices)) if adj[v]}
            self.assertEqual(nodes, set(b.land_vertices))
            seen_edges = set()
            for v, pairs in enumerate(adj):
                for e, n in pairs:
                    self.assertTrue(b.land_edge(e))
                    self.assertEqual(set(b.edge_vertices[e]), {v, n})
                    self.assertIn((e, v), adj[n])           # symmetric
                    seen_edges.add(e)
            self.assertEqual(seen_edges, set(b.land_edges))
            for v in range(len(b.vertices)):
                self.assertEqual(walkgraph.is_walkable_vertex(b, v), b.land_vertex(v))
            self.assertFalse(walkgraph.is_walkable_vertex(b, len(b.vertices)))
            self.assertFalse(walkgraph.is_walkable_vertex(b, -1))

    def test_edge_between(self) -> None:
        b = standard_board().board
        for e in b.land_edges:
            x, y = b.edge_vertices[e]
            self.assertEqual(walkgraph.edge_between(b, x, y), e)
            self.assertEqual(walkgraph.edge_between(b, y, x), e)
        sea_edges = [e for e in range(len(b.edges)) if not b.land_edge(e)]
        self.assertTrue(sea_edges)
        for e in sea_edges:
            x, y = b.edge_vertices[e]
            self.assertIsNone(walkgraph.edge_between(b, x, y))


class PathTest(unittest.TestCase):
    def test_uniform_costs_match_bfs(self) -> None:
        for gb in [standard_board(), generated(37, 5), generated(10, 2)]:
            state = bare_state(gb)
            b = gb.board
            ms = state.settings.settlers.ms_per_edge
            rng = Rng(11)
            land = list(b.land_vertices)
            for _ in range(40):
                a, z = rng.choice(land), rng.choice(land)
                hops = bfs_hops(b, a)[z]
                path = walkgraph.shortest_path(state, 0, a, z)
                self.assertIsNotNone(path)
                self.assertEqual(len(path), hops)
                if path:
                    self.assertEqual(path[-1], z)
                self.assertEqual(walkgraph.path_cost(state, 0, a, path), hops * ms)
                found = walkgraph.find_path(b, a, z, lambda e: ms)
                self.assertEqual(found, (hops * ms, path))
                # deterministic
                self.assertEqual(walkgraph.shortest_path(state, 0, a, z), path)

    def test_same_vertex_and_invalid_ends(self) -> None:
        state = bare_state()
        b = state.board.board
        v = b.land_vertices[0]
        self.assertEqual(walkgraph.shortest_path(state, 0, v, v), [])
        sea_v = next(i for i in range(len(b.vertices)) if not b.land_vertex(i))
        self.assertIsNone(walkgraph.shortest_path(state, 0, v, sea_v))
        self.assertIsNone(walkgraph.shortest_path(state, 0, sea_v, v))
        self.assertIsNone(walkgraph.shortest_path(state, 0, v, len(b.vertices)))

    def test_unreachable_between_islands(self) -> None:
        state = bare_state(two_islands())
        b = state.board.board
        a = b.hex_vertices[0][0]
        z = b.hex_vertices[1][0]
        self.assertTrue(b.land_vertex(a) and b.land_vertex(z))
        self.assertIsNone(walkgraph.shortest_path(state, 0, a, z))
        self.assertEqual(len(walkgraph.shortest_path(state, 0, a, b.hex_vertices[0][3])), 3)

    def test_path_cost_rejects_gaps(self) -> None:
        state = bare_state()
        b = state.board.board
        hv = b.hex_vertices[9]
        with self.assertRaises(EngineError):
            walkgraph.path_cost(state, 0, hv[0], [hv[2]])

    def test_road_speed_and_route_choice(self) -> None:
        state = bare_state(overrides={"settlers": {"ms_per_edge": 1500, "road_speed_pct": 200}})
        b = state.board.board
        hv = b.hex_vertices[9]                  # centre hex, clockwise from N
        a, z = hv[0], hv[3]                     # opposite corners: 3 edges either way round
        east = [hv[1], hv[2], hv[3]]
        west = [hv[5], hv[4], hv[3]]

        def edges(route: list[int]) -> list[int]:
            out, prev = [], a
            for v in route:
                out.append(walkgraph.edge_between(b, prev, v))
                prev = v
            return out

        self.assertEqual(walkgraph.path_cost(state, 0, a, east), 4500)
        for e in edges(west):
            state.roads[e] = 0
        self.assertEqual(walkgraph.edge_cost_ms(state, 0, edges(west)[0]), 750)
        self.assertEqual(walkgraph.edge_cost_ms(state, 1, edges(west)[0]), 1500)   # not own road
        self.assertEqual(walkgraph.shortest_path(state, 0, a, z), west)
        self.assertEqual(walkgraph.path_cost(state, 0, a, west), 2250)
        self.assertEqual(walkgraph.path_cost(state, 1, a, west), 4500)
        state.roads.clear()
        for e in edges(east):
            state.roads[e] = 0
        self.assertEqual(walkgraph.shortest_path(state, 0, a, z), east)

    def test_road_detour_preferred_when_cheaper(self) -> None:
        # 300 % speed: a 4-edge road detour (4 * 500) beats a 2-edge plain path (3000).
        state = bare_state(overrides={"settlers": {"ms_per_edge": 1500, "road_speed_pct": 300}})
        b = state.board.board
        hv = b.hex_vertices[9]
        a, z = hv[0], hv[2]
        self.assertEqual(walkgraph.shortest_path(state, 0, a, z), [hv[1], hv[2]])
        detour = [hv[5], hv[4], hv[3], hv[2]]
        prev = a
        for v in detour:
            state.roads[walkgraph.edge_between(b, prev, v)] = 0
            prev = v
        self.assertEqual(walkgraph.shortest_path(state, 0, a, z), detour)
        self.assertEqual(walkgraph.path_cost(state, 0, a, detour), 2000)
        self.assertEqual(walkgraph.shortest_path(state, 2, a, z), [hv[1], hv[2]])

    def test_integer_rounding(self) -> None:
        state = bare_state(overrides={"settlers": {"ms_per_edge": 1000, "road_speed_pct": 300}})
        e = state.board.board.land_edges[0]
        state.roads[e] = 1
        self.assertEqual(walkgraph.edge_cost_ms(state, 1, e), 333)


class LandingTest(unittest.TestCase):
    def check_spread(self, b: Board, points: list[int], count: int) -> None:
        cycle = walkgraph.landing_cycle(b)
        n = len(cycle)
        self.assertEqual(len(points), count)
        coastal = set(b.coastal_vertices)
        for v in points:
            self.assertIn(v, coastal)
            self.assertTrue(b.land_vertex(v))
        if count > n:
            return
        self.assertEqual(len(set(points)), count)
        idx = [cycle.index(v) for v in points]
        gaps = [(idx[(i + 1) % count] - idx[i]) % n or n for i in range(count)]
        self.assertEqual(sum(gaps), n)
        self.assertLessEqual(max(gaps) - min(gaps), 1)

    def test_landing_cycle_is_outer_coast(self) -> None:
        b = standard_board().board
        cycle = walkgraph.landing_cycle(b)
        self.assertEqual(len(cycle), 30)
        self.assertEqual(sorted(cycle), sorted(b.coastal_vertices))
        for i, v in enumerate(cycle):     # consecutive vertices joined by a walkable edge
            self.assertIsNotNone(walkgraph.edge_between(b, v, cycle[(i + 1) % len(cycle)]))

    def test_even_spread_many_boards(self) -> None:
        boards = [standard_board().board] + [generated(n, s).board for n in SIZES for s in (1, 2)]
        for b in boards:
            for count in (1, 2, 3, 4, 5, 6, 8, 12, 18):
                for seed in range(5):
                    self.check_spread(b, walkgraph.landing_points(b, count, Rng(seed)), count)

    def test_deterministic_and_offset_varies(self) -> None:
        b = standard_board().board
        self.assertEqual(walkgraph.landing_points(b, 4, Rng(9)), walkgraph.landing_points(b, 4, Rng(9)))
        firsts = {walkgraph.landing_points(b, 4, Rng(seed))[0] for seed in range(60)}
        self.assertGreater(len(firsts), 5)

    def test_one_draw_and_zero(self) -> None:
        b = standard_board().board
        r1, r2 = Rng(4), Rng(4)
        walkgraph.landing_points(b, 6, r1)
        r2.randbelow(len(walkgraph.landing_cycle(b)))
        self.assertEqual(r1, r2)
        r3 = Rng(4)
        self.assertEqual(walkgraph.landing_points(b, 0, r3), [])
        self.assertEqual(r3, Rng(4))

    def test_more_points_than_coast(self) -> None:
        b = generated(7, 1).board
        n = len(walkgraph.landing_cycle(b))
        pts = walkgraph.landing_points(b, n + 5, Rng(2))
        self.assertEqual(len(pts), n + 5)
        self.assertEqual(set(pts), set(walkgraph.landing_cycle(b)))

    def test_two_islands_uses_one_outer_coast(self) -> None:
        b = two_islands().board
        cycle = walkgraph.landing_cycle(b)
        self.assertEqual(len(cycle), 6)
        self.assertEqual(cycle, b.coastline_vertex_cycles()[0])

    def test_no_coast(self) -> None:
        with self.assertRaises(EngineError):
            walkgraph.landing_cycle(Board([], [(0, 0)]))


if __name__ == "__main__":
    unittest.main()
