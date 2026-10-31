import math
import unittest

from engine.board import coords
from engine.board.coords import (
    CORNER_ORDER, SIDE_ORDER, canon_edge, canon_vertex, edge_hexes, edge_vertices,
    hex_distance, hex_edges, hex_neighbors, hex_ring, hex_vertices, spiral,
    vertex_edges, vertex_hexes, vertex_neighbors, vertex_world_xy, vertex_xy2, world_xy,
)

REGION = spiral((0, 0), 127)  # radius 6


def _key(x: float, y: float) -> tuple[int, int]:
    return (round(x * 1000), round(y * 1000))


def _corner_xy(h: tuple[int, int], i: int) -> tuple[float, float]:
    """Float corner i (0=N, clockwise) computed independently by angle."""
    cx = math.sqrt(3) * (h[0] + h[1] / 2)
    cy = 1.5 * h[1]
    a = math.radians(60 * i - 90)  # screen y down: -90 deg is north
    return (cx + math.cos(a), cy + math.sin(a))


class GeometryTest(unittest.TestCase):
    def test_vertex_canonicalisation_matches_world_space(self) -> None:
        by_pos: dict[tuple[int, int], set] = {}
        by_key: dict[tuple, set] = {}
        for h in REGION:
            for i, c in enumerate(CORNER_ORDER):
                pos = _key(*_corner_xy(h, i))
                k = canon_vertex(h[0], h[1], c)
                by_pos.setdefault(pos, set()).add(k)
                by_key.setdefault(k, set()).add(pos)
        for pos, keys in by_pos.items():
            self.assertEqual(len(keys), 1, f"position {pos} has keys {keys}")
        for k, poss in by_key.items():
            self.assertEqual(len(poss), 1, f"key {k} has positions {poss}")
            self.assertIn(k[2], ("N", "S"))
            self.assertEqual(_key(*vertex_world_xy(k)), next(iter(poss)))

    def test_edge_canonicalisation_matches_world_space(self) -> None:
        by_pos: dict[tuple[int, int], set] = {}
        by_key: dict[tuple, set] = {}
        for h in REGION:
            for i, s in enumerate(SIDE_ORDER):
                a = _corner_xy(h, i)
                b = _corner_xy(h, (i + 1) % 6)
                pos = _key((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                k = canon_edge(h[0], h[1], s)
                by_pos.setdefault(pos, set()).add(k)
                by_key.setdefault(k, set()).add(pos)
                # the edge's vertices are the two corners in world space
                ends = {_key(*vertex_world_xy(v)) for v in edge_vertices(k)}
                self.assertEqual(ends, {_key(*a), _key(*b)})
        for keys in by_pos.values():
            self.assertEqual(len(keys), 1)
        for k, poss in by_key.items():
            self.assertEqual(len(poss), 1)
            self.assertIn(k[2], ("NE", "E", "SE"))

    def test_neighbour_side_faces_neighbour(self) -> None:
        for h in REGION[:19]:
            for n, e in zip(hex_neighbors(h), hex_edges(h)):
                self.assertEqual(set(edge_hexes(e)), {h, n})
                d = math.dist(world_xy(h), world_xy(n))
                self.assertAlmostEqual(d, math.sqrt(3))

    def test_integer_coordinates_match_floats(self) -> None:
        for h in REGION[:37]:
            for v in hex_vertices(h):
                x2, y2 = vertex_xy2(v)
                fx, fy = vertex_world_xy(v)
                self.assertAlmostEqual(fx, x2 * math.sqrt(3) / 2)
                self.assertAlmostEqual(fy, y2 / 2)


class ConsistencyTest(unittest.TestCase):
    def test_invalid_names(self) -> None:
        with self.assertRaises(ValueError):
            canon_vertex(0, 0, "X")
        with self.assertRaises(ValueError):
            canon_edge(0, 0, "N")

    def test_canonical_is_idempotent(self) -> None:
        for h in REGION:
            for v in hex_vertices(h):
                self.assertEqual(canon_vertex(*v), v)
            for e in hex_edges(h):
                self.assertEqual(canon_edge(*e), e)

    def test_hex_vertices_and_edges_agree(self) -> None:
        for h in REGION:
            vs = hex_vertices(h)
            es = hex_edges(h)
            self.assertEqual(len(set(vs)), 6)
            self.assertEqual(len(set(es)), 6)
            for v in vs:
                self.assertIn(h, vertex_hexes(v))
            for i, e in enumerate(es):
                self.assertIn(h, edge_hexes(e))
                self.assertEqual(set(edge_vertices(e)), {vs[i], vs[(i + 1) % 6]})

    def test_vertex_edges_neighbours_hexes_agree(self) -> None:
        for h in REGION:
            for v in hex_vertices(h):
                hs = vertex_hexes(v)
                es = vertex_edges(v)
                ns = vertex_neighbors(v)
                self.assertEqual(len(set(hs)), 3)
                self.assertEqual(len(set(es)), 3)
                self.assertEqual(len(set(ns)), 3)
                for i, e in enumerate(es):
                    self.assertIn(v, edge_vertices(e))
                    self.assertEqual(set(edge_hexes(e)), {hs[i], hs[(i + 1) % 3]})
                    self.assertEqual(set(edge_vertices(e)), {v, ns[i]})
                    self.assertIn(v, vertex_neighbors(ns[i]))
                for x in hs:
                    self.assertIn(v, hex_vertices(x))
                # hexes pairwise adjacent
                for i in range(3):
                    self.assertEqual(hex_distance(hs[i], hs[(i + 1) % 3]), 1)

    def test_edge_hexes_and_vertices(self) -> None:
        for h in REGION:
            for e in hex_edges(h):
                a, b = edge_hexes(e)
                self.assertEqual(hex_distance(a, b), 1)
                for v in edge_vertices(e):
                    self.assertIn(e, vertex_edges(v))
                    self.assertIn(a, vertex_hexes(v))
                    self.assertIn(b, vertex_hexes(v))

    def test_neighbour_symmetry(self) -> None:
        for h in REGION:
            ns = hex_neighbors(h)
            self.assertEqual(len(set(ns)), 6)
            for n in ns:
                self.assertIn(h, hex_neighbors(n))
                self.assertEqual(hex_distance(h, n), 1)

    def test_distance_properties(self) -> None:
        sample = REGION[::7]
        for a in sample:
            self.assertEqual(hex_distance(a, a), 0)
            for b in sample:
                self.assertEqual(hex_distance(a, b), hex_distance(b, a))
                for c in sample[::3]:
                    self.assertLessEqual(hex_distance(a, c), hex_distance(a, b) + hex_distance(b, c))


class RingSpiralTest(unittest.TestCase):
    def test_ring_sizes_and_distance(self) -> None:
        for center in [(0, 0), (3, -2), (-5, 7)]:
            self.assertEqual(hex_ring(center, 0), [center])
            for radius in range(1, 8):
                ring = hex_ring(center, radius)
                self.assertEqual(len(ring), 6 * radius)
                self.assertEqual(len(set(ring)), 6 * radius)
                for h in ring:
                    self.assertEqual(hex_distance(center, h), radius)
                # consecutive ring hexes are adjacent, and the ring closes
                for i, h in enumerate(ring):
                    self.assertEqual(hex_distance(h, ring[(i + 1) % len(ring)]), 1)
                self.assertEqual(ring[0], (center[0] + radius, center[1] - radius))

    def test_spiral_unique_and_ordered(self) -> None:
        s = spiral((0, 0), 400)
        self.assertEqual(len(set(s)), 400)
        dists = [hex_distance((0, 0), h) for h in s]
        self.assertEqual(dists, sorted(dists))
        self.assertEqual(len(spiral((0, 0), 19)), 19)
        self.assertEqual(max(hex_distance((0, 0), h) for h in spiral((0, 0), 19)), 2)
        self.assertEqual(spiral((0, 0), 7), [(0, 0)] + hex_ring((0, 0), 1))
        self.assertEqual(spiral((0, 0), 0), [])
        # prefix property
        for n in (1, 5, 19, 50):
            self.assertEqual(spiral((0, 0), n), s[:n])

    def test_integer_geometry_is_int(self) -> None:
        self.assertIsInstance(coords.vertex_xy2((0, 0, "N"))[0], int)


if __name__ == "__main__":
    unittest.main()
