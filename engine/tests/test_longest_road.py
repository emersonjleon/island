"""Longest Road (stage 2): lengths on the fixture board, the award and its points."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from collections.abc import Iterator

from engine import game
from engine.events import LongestRoad, Points
from engine.rules import longest_road, victory
from engine.settings.enums import BuildKind
from engine.state import GameState
from engine.tests.test_dice import make_state, place, wp7_registry

R, S, C = BuildKind.ROAD, BuildKind.SETTLEMENT, BuildKind.CITY


@contextmanager
def registry() -> Iterator[None]:
    with wp7_registry():
        game.connect(game.SIG_BUILT, order=longest_road.BUILT_ORDER)(longest_road.on_built)
        yield


def chain(state: GameState, start: int, n: int, avoid: set[int] | None = None) -> list[int]:
    """Edges of a simple path of ``n`` segments from vertex ``start`` (greedy walk)."""
    board = state.board.board
    seen_v, edges, v = {start}, [], start
    avoid = avoid or set()
    while len(edges) < n:
        for e, w in zip(board.vertex_edges[v], board.vertex_neighbors[v]):
            if w not in seen_v and e not in avoid and board.land_vertex(w):
                edges.append(e)
                seen_v.add(w)
                v = w
                break
        else:
            raise AssertionError("no path long enough from the start vertex")
    return edges


def path_vertices(state: GameState, start: int, edges: list[int]) -> list[int]:
    out, v = [start], start
    for e in edges:
        a, b = state.board.board.edge_vertices[e]
        v = b if a == v else a
        out.append(v)
    return out


class LongestRoadTest(unittest.TestCase):
    def setUp(self) -> None:
        self._reg = registry()
        self._reg.__enter__()

    def tearDown(self) -> None:
        self._reg.__exit__(None, None, None)

    def build_road(self, s: GameState, seat: int, edge: int, now: int = 1) -> list:
        s.roads[edge] = seat
        return game.emit(s, game.SIG_BUILT, now, seat=seat, kind=R, target=edge, setup=False, construction=0)

    def build_settlement(self, s: GameState, seat: int, v: int, now: int = 1) -> list:
        place(s, seat, v)
        return game.emit(s, game.SIG_BUILT, now, seat=seat, kind=S, target=v, setup=False, construction=0)

    def start_vertex(self, s: GameState) -> int:
        return next(v for v in range(len(s.board.board.vertices))
                    if s.board.board.land_vertex(v) and len(s.board.board.vertex_edges[v]) == 3)

    # ------------------------------------------------------------ length
    def test_length_of_a_chain_and_a_fork(self) -> None:
        s = make_state()
        v0 = self.start_vertex(s)
        edges = chain(s, v0, 4)
        for e in edges:
            s.roads[e] = 0
        self.assertEqual(longest_road.road_length(s, 0), 4)
        # A branch off the start vertex: the trail can use only two of the three ends.
        branch = next(e for e in s.board.board.vertex_edges[v0] if e not in edges)
        s.roads[branch] = 0
        self.assertEqual(longest_road.road_length(s, 0), 5)
        self.assertEqual(longest_road.road_length(s, 1), 0)

    def test_opponent_building_splits_the_road(self) -> None:
        s = make_state()
        v0 = self.start_vertex(s)
        edges = chain(s, v0, 5)
        for e in edges:
            s.roads[e] = 0
        middle = path_vertices(s, v0, edges)[2]
        place(s, 0, middle)
        self.assertEqual(longest_road.road_length(s, 0), 5)     # own building: no split
        place(s, 1, middle)
        self.assertEqual(longest_road.road_length(s, 0), 3)     # 2 + 3 segments, longest is 3

    # ------------------------------------------------------------ award
    def test_next_holder_rules(self) -> None:
        nh = longest_road.next_holder
        self.assertIsNone(nh(None, {0: 4, 1: 3}, 5))            # below the minimum
        self.assertEqual(nh(None, {0: 5, 1: 3}, 5), 0)          # first to reach it
        self.assertEqual(nh(0, {0: 5, 1: 5}, 5), 0)             # holder keeps a tie
        self.assertEqual(nh(0, {0: 5, 1: 6}, 5), 1)             # strictly longer takes it
        self.assertIsNone(nh(0, {0: 3, 1: 6, 2: 6}, 5))         # split holder, others tied
        self.assertEqual(nh(0, {0: 3, 1: 6, 2: 5}, 5), 1)
        self.assertIsNone(nh(0, {0: 3, 1: 4}, 5))               # nobody long enough any more

    def test_award_points_and_events(self) -> None:
        s = make_state()
        v0 = self.start_vertex(s)
        edges = chain(s, v0, 5)
        for e in edges[:4]:
            self.build_road(s, 0, e)
        self.assertIsNone(longest_road.holder(s))
        self.assertEqual(longest_road.lengths(s), {0: 4, 1: 0, 2: 0})
        ev = self.build_road(s, 0, edges[4], now=7)
        self.assertEqual(ev, [LongestRoad(at=7, seat=0, previous=None, lengths={0: 5, 1: 0, 2: 0}),
                              Points(at=7, seat=0, points=2)])
        self.assertEqual(longest_road.holder(s), 0)

        # Seat 1 founds a settlement in the middle: seat 0 drops to 3, nobody holds it.
        middle = path_vertices(s, v0, edges)[2]
        ev = self.build_settlement(s, 1, middle, now=9)
        self.assertIn(LongestRoad(at=9, seat=None, previous=0, lengths={0: 3, 1: 0, 2: 0}), ev)
        self.assertIn(Points(at=9, seat=0, points=0), ev)
        self.assertEqual(s.players[1].points, 1)                # the settlement itself
        self.assertIsNone(longest_road.holder(s))

    def test_a_city_or_unchanged_lengths_emit_nothing(self) -> None:
        s = make_state()
        v0 = self.start_vertex(s)
        e = chain(s, v0, 1)[0]
        self.assertTrue(any(isinstance(x, LongestRoad) for x in self.build_road(s, 0, e)))
        far = next(v for v in range(len(s.board.board.vertices)) if v not in s.board.board.edge_vertices[e])
        self.assertFalse(any(isinstance(x, LongestRoad) for x in self.build_settlement(s, 2, far)))
        ev = game.emit(s, game.SIG_BUILT, 3, seat=2, kind=C, target=far, setup=False, construction=0)
        self.assertFalse(any(isinstance(x, LongestRoad) for x in ev))

    def test_award_can_win_the_game(self) -> None:
        s = make_state(overrides={"victory": {"target": 5}})
        s.players[0].points = 3
        v0 = self.start_vertex(s)
        for e in chain(s, v0, 5):
            self.build_road(s, 0, e, now=11)
        self.assertEqual(s.phase, "finished")
        self.assertEqual((s.winner, s.players[0].points), (0, 5))

    def test_points_and_minimum_from_settings(self) -> None:
        s = make_state(overrides={"victory": {"longest_road": {"min": 3, "points": 4}}}, stage=2)
        v0 = self.start_vertex(s)
        for e in chain(s, v0, 3):
            self.build_road(s, 1, e)
        self.assertEqual((longest_road.holder(s), s.players[1].points), (1, 4))

    def test_finished_game_is_frozen(self) -> None:
        s = make_state()
        victory.finish(s, 0, 1)
        e = chain(s, self.start_vertex(s), 1)[0]
        self.assertEqual(self.build_road(s, 1, e), [])


if __name__ == "__main__":
    unittest.main()
