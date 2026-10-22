import unittest

from engine.board import coords
from engine.board.topology import Board, sea_around


def _lcg(seed: int):
    state = seed
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        yield state >> 33


class StandardIslandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.b = Board.spiral_island(19, sea_margin=0)

    def test_counts(self) -> None:
        b = self.b
        self.assertEqual(len(b.hexes), 19)
        self.assertEqual(len(b.land_vertices), 54)
        self.assertEqual(len(b.vertices), 54)
        self.assertEqual(len(b.land_edges), 72)
        self.assertEqual(len(b.coastal_edges), 30)
        self.assertEqual(len(b.coastal_vertices), 30)
        cycles = b.coastline_cycles()
        self.assertEqual(len(cycles), 1)
        self.assertEqual(len(cycles[0]), 30)
        self.assertEqual(sorted(cycles[0]), list(b.coastal_edges))
        self.assertEqual(cycles[0][0], min(b.coastal_edges))
        self.assertEqual(b.coastline_is_outer(), [True])

    def test_with_sea(self) -> None:
        b = Board.spiral_island(19, sea_margin=1)
        self.assertEqual(len(b.land_hex_ids), 19)
        self.assertEqual(len(b.sea_hex_ids), 18)
        self.assertTrue(all(b.is_land(h) for h in b.land_hex_ids))
        self.assertFalse(any(b.is_land(h) for h in b.sea_hex_ids))
        self.assertEqual(len(b.land_vertices), 54)
        self.assertEqual(len(b.land_edges), 72)
        self.assertEqual(len(b.coastal_edges), 30)
        self.assertEqual(len(b.coastline_cycles()[0]), 30)
        for e in b.coastal_edges:
            self.assertEqual(len(b.edge_hexes[e]), 2)
            self.assertEqual(sorted(b.is_land(h) for h in b.edge_hexes[e]), [False, True])
        for v in range(len(b.vertices)):
            self.assertEqual(b.land_vertex(v), any(b.is_land(h) for h in b.vertex_hexes[v]))

    def test_land_first_ids(self) -> None:
        b = Board.spiral_island(19, sea_margin=2)
        land = list(b.hexes[: b.land_hex_count])
        sea = list(b.hexes[b.land_hex_count:])
        self.assertEqual(land, sorted(land))
        self.assertEqual(sea, sorted(sea))
        self.assertEqual(set(land), set(coords.spiral((0, 0), 19)))
        self.assertEqual(list(b.vertices), sorted(b.vertices))
        self.assertEqual(list(b.edges), sorted(b.edges))


class CoastlineTest(unittest.TestCase):
    def _check_cycles(self, b: Board) -> None:
        e_cycles = b.coastline_cycles()
        v_cycles = b.coastline_vertex_cycles()
        self.assertEqual(len(e_cycles), len(v_cycles))
        all_edges: list[int] = []
        for es, vs in zip(e_cycles, v_cycles):
            self.assertEqual(len(es), len(vs))
            self.assertEqual(es[0], min(es))
            self.assertEqual(len(set(vs)), len(vs))
            n = len(es)
            for i in range(n):
                self.assertEqual(set(b.edge_vertices[es[i]]), {vs[i], vs[(i + 1) % n]})
                shared = set(b.edge_vertices[es[i]]) & set(b.edge_vertices[es[(i + 1) % n]])
                self.assertEqual(len(shared), 1)
                # land is on the right of the walking direction (screen y down)
                ax, ay = coords.vertex_xy2(b.vertices[vs[i]])
                bx, by = coords.vertex_xy2(b.vertices[vs[(i + 1) % n]])
                land = [h for h in b.edge_hexes[es[i]] if b.is_land(h)]
                self.assertEqual(len(land), 1)
                hx, hy = coords.hex_xy2(b.hexes[land[0]])
                self.assertGreater((bx - ax) * (hy - ay) - (by - ay) * (hx - ax), 0)
            all_edges.extend(es)
        self.assertEqual(sorted(all_edges), list(b.coastal_edges))
        outer = b.coastline_is_outer()
        self.assertEqual(outer, sorted(outer, reverse=True))

    def test_spiral_boards(self) -> None:
        for n in (1, 2, 3, 7, 10, 19, 37, 61, 100, 250):
            b = Board.spiral_island(n, sea_margin=1)
            self._check_cycles(b)
            self.assertEqual(len(b.coastline_cycles()), 1)
            self.assertEqual(b.coastline_is_outer(), [True])

    def test_lake_gives_two_cycles(self) -> None:
        land = [h for h in coords.spiral((0, 0), 37) if h != (0, 0)]
        for sea in ([(0, 0)], []):
            b = Board.from_hexes(land, sea)
            self._check_cycles(b)
            cycles = b.coastline_cycles()
            self.assertEqual(len(cycles), 2)
            self.assertEqual(b.coastline_is_outer(), [True, False])
            self.assertEqual(len(cycles[0]), 42)
            self.assertEqual(len(cycles[1]), 6)

    def test_two_islands(self) -> None:
        land = coords.spiral((0, 0), 7) + coords.spiral((10, 0), 7)
        b = Board.from_hexes(land, sea_around(land, 1))
        self._check_cycles(b)
        self.assertEqual(b.coastline_is_outer(), [True, True])
        self.assertEqual([len(c) for c in b.coastline_cycles()], [18, 18])

    def test_random_blobs(self) -> None:
        for seed in range(30):
            rnd = _lcg(seed)
            land = {(0, 0)}
            target = 5 + next(rnd) % 60
            while len(land) < target:
                pick = sorted(land)[next(rnd) % len(land)]
                land.add(coords.hex_neighbors(pick)[next(rnd) % 6])
            b = Board.from_hexes(land, sea_around(land, 1))
            self._check_cycles(b)
            self.assertGreaterEqual(b.coastline_is_outer().count(True), 1)


class StructureTest(unittest.TestCase):
    def test_euler(self) -> None:
        for n in (7, 19, 37, 61, 100, 250):
            b = Board.spiral_island(n, sea_margin=0)
            v, e, f = len(b.land_vertices), len(b.land_edges), len(b.land_hex_ids)
            self.assertEqual(v - e + f, 1, n)

    def test_ids_stable_across_rebuilds(self) -> None:
        a = Board.spiral_island(61, sea_margin=2)
        land = list(a.hexes[: a.land_hex_count])
        sea = list(a.hexes[a.land_hex_count:])
        b = Board.from_hexes(reversed(land), reversed(sea))
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.coastline_cycles(), b.coastline_cycles())
        self.assertEqual(a.coastline_vertex_cycles(), b.coastline_vertex_cycles())

    def test_overlap_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Board.from_hexes([(0, 0)], [(0, 0)])

    def test_adjacency_tables_agree(self) -> None:
        b = Board.spiral_island(37, sea_margin=1)
        for h in range(len(b.hexes)):
            self.assertEqual(len(b.hex_vertices[h]), 6)
            self.assertEqual(len(b.hex_edges[h]), 6)
            for v in b.hex_vertices[h]:
                self.assertIn(h, b.vertex_hexes[v])
            for e in b.hex_edges[h]:
                self.assertIn(h, b.edge_hexes[e])
            for n in b.hex_neighbors[h]:
                self.assertIn(h, b.hex_neighbors[n])
                self.assertEqual(len(set(b.hex_edges[h]) & set(b.hex_edges[n])), 1)
        for v in range(len(b.vertices)):
            self.assertIn(len(b.vertex_edges[v]), (2, 3))
            self.assertEqual(len(b.vertex_edges[v]), len(b.vertex_neighbors[v]))
            for e, n in zip(b.vertex_edges[v], b.vertex_neighbors[v]):
                self.assertEqual(set(b.edge_vertices[e]), {v, n})
                self.assertIn(v, b.vertex_neighbors[n])
            for h in b.vertex_hexes[v]:
                self.assertIn(v, b.hex_vertices[h])
        for e in range(len(b.edges)):
            self.assertEqual(len(b.edge_vertices[e]), 2)
            for v in b.edge_vertices[e]:
                self.assertIn(e, b.vertex_edges[v])
            self.assertIn(len(b.edge_hexes[e]), (1, 2))
            self.assertEqual(b.land_edge(e), any(b.is_land(h) for h in b.edge_hexes[e]))
            self.assertEqual(b.coastal_edge(e), sum(b.is_land(h) for h in b.edge_hexes[e]) == 1)
        # interior land vertices have full degree
        for v in b.land_vertices:
            if len(b.vertex_hexes[v]) == 3:
                self.assertEqual(len(b.vertex_edges[v]), 3)
        for key, i in b.vertex_id.items():
            self.assertEqual(b.vertices[i], key)
        for key, i in b.edge_id.items():
            self.assertEqual(b.edges[i], key)
        for key, i in b.hex_id.items():
            self.assertEqual(b.hexes[i], key)

    def test_to_dict_shape(self) -> None:
        b = Board.spiral_island(7, sea_margin=1)
        d = b.to_dict()
        self.assertEqual(set(d), {"hexes", "vertices", "edges"})
        self.assertEqual(d["hexes"][0], {"id": 0, "q": b.hexes[0][0], "r": b.hexes[0][1]})
        v0 = d["vertices"][0]
        self.assertEqual(set(v0), {"id", "q", "r", "c", "hexes", "adj_v", "adj_e"})
        self.assertIn(v0["c"], ("N", "S"))
        e0 = d["edges"][0]
        self.assertEqual(set(e0), {"id", "v", "hexes"})
        self.assertEqual(len(e0["v"]), 2)
        self.assertEqual(len(d["hexes"]), 7 + 12)


if __name__ == "__main__":
    unittest.main()
