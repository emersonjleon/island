"""Board generator (WP3): classic board, invariants over many seeds and sizes, determinism, errors."""
import time
import unittest
from collections import Counter

from engine.board import coords
from engine.board.generator import BoardGenerationError, check_board_settings, generate_board
from engine.board.model import GeneratedBoard
from engine.rng import Rng
from engine.settings import (
    TERRAIN_RESOURCE, GameSettings, Resource, Terrain, load_preset, resolve_board_counts,
)

SEEDS = range(200)

# Land size -> board overrides. Fishing grounds and generic harbors auto-scale with the
# coastline, so every size works with the defaults.
SIZES: dict[int, dict] = {n: {} for n in (7, 10, 19, 37, 61, 100, 250)}


def settings_for(land: int, **board: object) -> GameSettings:
    return load_preset("classic", {"board": {"land_hexes": land, **SIZES.get(land, {}), **board}})


def red_hexes(g: GeneratedBoard, red: set[int], include_fishing: bool) -> list[int]:
    return [h for h, t in enumerate(g.token)
            if t in red and (g.board.is_land(h) or (include_fishing and h in g.fishing))]


class InvariantMixin:
    def check_invariants(self, g: GeneratedBoard, s: GameSettings) -> None:
        tc: unittest.TestCase = self  # type: ignore[assignment]
        b = g.board
        bs = s.board
        counts = resolve_board_counts(s)
        # terrain: None exactly on sea, counts match
        tc.assertEqual(len(g.terrain), len(b.hexes))
        for h in range(len(b.hexes)):
            tc.assertEqual(g.terrain[h] is None, not b.is_land(h))
        tc.assertEqual(Counter(t for t in g.terrain if t is not None),
                       +Counter({t: n for t, n in counts.terrain_counts.items()}))
        # land is connected
        land = set(b.land_hex_ids)
        seen, stack = {0}, [0]
        while stack:
            for n in b.hex_neighbors[stack.pop()]:
                if n in land and n not in seen:
                    seen.add(n)
                    stack.append(n)
        tc.assertEqual(seen, land)
        # tokens: only on producing land hexes and fishing grounds, multisets match
        producing = {h for h in land if TERRAIN_RESOURCE[g.terrain[h]] is not None}
        for h, t in enumerate(g.token):
            tc.assertEqual(t is not None, h in producing or h in g.fishing, h)
        tc.assertEqual(sorted(g.token[h] for h in producing), sorted(counts.number_tokens))
        tc.assertEqual(sorted(g.token[h] for h in g.fishing), sorted(counts.fishing_tokens))
        # fishing grounds: distinct sea hexes next to land, respecting min_gap
        tc.assertEqual(len(g.fishing), counts.fishing_count)
        for h in g.fishing:
            tc.assertFalse(b.is_land(h))
            tc.assertTrue(any(b.is_land(n) for n in b.hex_neighbors[h]))
        fl = sorted(g.fishing)
        for i, a in enumerate(fl):
            for c in fl[i + 1:]:
                tc.assertGreaterEqual(coords.hex_distance(b.hexes[a], b.hexes[c]),
                                      bs.fishing_grounds.min_gap + 1)
        # red rule
        if not bs.red_may_touch:
            reds = set(red_hexes(g, set(bs.red_numbers), bs.red_rule_includes_fishing))
            for h in reds:
                tc.assertFalse(reds.intersection(b.hex_neighbors[h]), f"adjacent red hexes at {h}")
        # harbors: on the outer coast, vertex-disjoint, types match
        outer = set(b.coastline_cycles()[b.coastline_is_outer().index(True)])
        tc.assertEqual(len(g.harbors), counts.harbors_total)
        used: set[int] = set()
        for hb in g.harbors:
            tc.assertTrue(b.coastal_edge(hb.edge))
            tc.assertIn(hb.edge, outer)
            tc.assertEqual(hb.vertices, b.edge_vertices[hb.edge])
            tc.assertFalse(used.intersection(hb.vertices))
            used.update(hb.vertices)
            tc.assertEqual(hb.ratio, bs.harbors.generic_ratio if hb.resource is None else bs.harbors.specific_ratio)
        kinds = Counter(hb.resource for hb in g.harbors)
        tc.assertEqual(kinds[None], counts.harbors_generic)
        for r, n in counts.harbors_specific.items():
            tc.assertEqual(kinds[r], n)
        # robber
        tc.assertIsNotNone(g.robber_start)
        tc.assertTrue(b.is_land(g.robber_start))
        if counts.terrain_counts[Terrain.DESERT] and bs.robber_start == "desert":
            tc.assertEqual(g.terrain[g.robber_start], Terrain.DESERT)


class ClassicBoardTest(InvariantMixin, unittest.TestCase):
    def test_standard_board(self) -> None:
        s = load_preset("classic")
        for seed in range(20):
            g = generate_board(s, Rng(seed))
            b = g.board
            self.assertEqual(b.land_hex_count, 19)
            deserts = [h for h in b.land_hex_ids if g.terrain[h] == Terrain.DESERT]
            self.assertEqual(len(deserts), 1)
            self.assertIsNone(g.token[deserts[0]])
            land_tokens = sorted(g.token[h] for h in b.land_hex_ids if g.token[h] is not None)
            self.assertEqual(land_tokens, [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12])
            self.assertEqual(len(g.fishing), 6)
            self.assertEqual(sorted(g.token[h] for h in g.fishing), [4, 5, 6, 8, 9, 10])
            self.assertEqual(len(g.harbors), 9)
            generic = [h for h in g.harbors if h.resource is None]
            self.assertEqual(len(generic), 4)
            self.assertTrue(all(h.ratio == 3 for h in generic))
            specific = sorted(h.resource.value for h in g.harbors if h.resource is not None)
            self.assertEqual(specific, sorted(r.value for r in
                                              (Resource.LUMBER, Resource.BRICK, Resource.WOOL,
                                               Resource.GRAIN, Resource.ORE)))
            self.assertTrue(all(h.ratio == 2 for h in g.harbors if h.resource is not None))
            self.assertEqual(g.robber_start, deserts[0])
            self.check_invariants(g, s)

    def test_classic_harbors_avoid_fishing_grounds(self) -> None:
        s = load_preset("classic")
        for seed in range(50):
            g = generate_board(s, Rng(seed))
            for hb in g.harbors:
                sea = [h for h in g.board.edge_hexes[hb.edge] if not g.board.is_land(h)]
                self.assertNotIn(sea[0], g.fishing)

    def test_check_board_settings_classic(self) -> None:
        check_board_settings(load_preset("classic"))
        check_board_settings(load_preset("blitz"))


class InvariantTest(InvariantMixin, unittest.TestCase):
    def test_sizes_and_seeds(self) -> None:
        for land in SIZES:
            s = settings_for(land)
            for seed in SEEDS:
                with self.subTest(land=land, seed=seed):
                    self.check_invariants(generate_board(s, Rng(seed)), s)

    def test_variants(self) -> None:
        variants = [
            {"red_rule_includes_fishing": False},
            {"red_may_touch": True},
            {"fishing_grounds": {"count": 0}, "harbors": {"generic": 0, "specific": {}}},
            {"fishing_grounds": {"count": 6, "min_gap": 0}},
            {"fishing_grounds": {"count": 4, "min_gap": 2}},
            {"robber_start": "random_land"},
            {"sea_margin": 1},
            {"harbors": {"generic": 2, "specific": {"fish": 2, "ore": 3}, "generic_ratio": 4,
                         "specific_ratio": 1}},
        ]
        for v in variants:
            for land in (7, 19, 37):
                s = settings_for(land, **v)
                for seed in range(40):
                    with self.subTest(variant=v, land=land, seed=seed):
                        self.check_invariants(generate_board(s, Rng(seed)), s)

    def test_robber_random_land_and_no_desert(self) -> None:
        s = settings_for(7)  # 7 land hexes: auto counts have no desert
        self.assertEqual(resolve_board_counts(s).terrain_counts[Terrain.DESERT], 0)
        starts = {generate_board(s, Rng(seed)).robber_start for seed in range(60)}
        self.assertGreater(len(starts), 1)
        s = settings_for(19, robber_start="random_land")
        g_starts = {generate_board(s, Rng(seed)).robber_start for seed in range(60)}
        self.assertGreater(len(g_starts), 1)

    def test_robber_disabled(self) -> None:
        s = load_preset("classic", {"robber": {"enabled": False}})
        self.assertIsNone(generate_board(s, Rng(1)).robber_start)


class DeterminismTest(unittest.TestCase):
    def test_same_seed_same_board(self) -> None:
        for land in (7, 19, 100):
            s = settings_for(land)
            for seed in range(10):
                self.assertEqual(generate_board(s, Rng(seed)).to_dict(), generate_board(s, Rng(seed)).to_dict())

    def test_rng_state_advances_identically(self) -> None:
        s = load_preset("classic")
        a, b = Rng(5), Rng(5)
        generate_board(s, a)
        generate_board(s, b)
        self.assertEqual(a.state, b.state)

    def test_different_seeds_differ(self) -> None:
        s = load_preset("classic")
        boards = {repr(generate_board(s, Rng(seed)).to_dict()) for seed in range(30)}
        self.assertGreaterEqual(len(boards), 29)

    def test_seeded_layout_uses_board_seed(self) -> None:
        s = load_preset("classic", {"board": {"layout": "seeded", "seed": 1234}})
        rng = Rng(99)
        before = rng.state
        g1 = generate_board(s, rng)
        self.assertEqual(rng.state, before, "seeded layout must not consume the game rng")
        g2 = generate_board(s, Rng(7))
        self.assertEqual(g1.to_dict(), g2.to_dict())
        plain = generate_board(load_preset("classic"), Rng(1234))
        self.assertEqual(g1.to_dict(), plain.to_dict())
        other = generate_board(load_preset("classic", {"board": {"layout": "seeded", "seed": 1235}}), Rng(7))
        self.assertNotEqual(g1.to_dict(), other.to_dict())

    def test_seeded_layout_without_seed_uses_rng(self) -> None:
        s = load_preset("classic", {"board": {"layout": "seeded"}})
        self.assertEqual(generate_board(s, Rng(3)).to_dict(),
                         generate_board(load_preset("classic"), Rng(3)).to_dict())


class ErrorTest(unittest.TestCase):
    def assert_code(self, s: GameSettings, code: str) -> None:
        with self.assertRaises(BoardGenerationError) as cm:
            check_board_settings(s)
        self.assertEqual(cm.exception.code, code)
        self.assertIsInstance(cm.exception.params, dict)
        self.assertIsInstance(cm.exception, ValueError)

    def test_too_many_harbors(self) -> None:
        self.assert_code(settings_for(7, harbors={"generic": 20}), "board.harbors_unplaceable")

    def test_too_many_fishing_grounds(self) -> None:
        self.assert_code(settings_for(7, fishing_grounds={"count": 13}), "board.fishing_grounds_unplaceable")
        self.assert_code(settings_for(19, fishing_grounds={"count": 8, "min_gap": 3}),
                         "board.fishing_grounds_unplaceable")

    def test_red_forced_adjacent(self) -> None:
        # 7 land hexes, no desert: at most 3 pairwise non-adjacent hexes, but 4 red tokens.
        s = settings_for(7, number_tokens={6: 2, 8: 2, 5: 1, 9: 1, 4: 1})
        self.assert_code(s, "board.red_rule_unsatisfiable")
        check_board_settings(settings_for(7, number_tokens={6: 2, 8: 2, 5: 1, 9: 1, 4: 1}, red_may_touch=True))

    def test_red_fishing_forced_adjacent(self) -> None:
        # Every fishing token red and min_gap 0 on a full coast: red fishing grounds must touch.
        s = settings_for(7, fishing_grounds={"count": 12, "min_gap": 0, "tokens": [6]})
        self.assert_code(s, "board.red_rule_unsatisfiable")
        check_board_settings(settings_for(7, fishing_grounds={"count": 12, "min_gap": 0, "tokens": [6]},
                                          red_rule_includes_fishing=False))

    def test_auto_counts_fit_every_size(self) -> None:
        for land in (7, 10, 19, 37, 61, 100, 150, 200, 250):
            with self.subTest(land=land):
                check_board_settings(load_preset("classic", {"board": {"land_hexes": land}}))


class PerformanceTest(unittest.TestCase):
    def test_large_board_fast(self) -> None:
        s = settings_for(250)
        t0 = time.perf_counter()
        generate_board(s, Rng(42))
        self.assertLess(time.perf_counter() - t0, 0.5)


if __name__ == "__main__":
    unittest.main()
