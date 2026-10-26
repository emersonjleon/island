"""The invariant checker itself catches broken states (WP8)."""
import unittest

from engine.settings.enums import BuildKind, Resource
from engine.sim import invariants
from engine.sim.runner import run_game
from engine.state import Building
from engine.tests.fixtures import make_seats, make_settings


class InvariantCheckerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.r = run_game(make_settings(), make_seats(3), 2, ["greedy"] * 3, 300_000)
        self.st = self.r.state
        self.totals = invariants.resource_totals(self.st)
        self.assertEqual(invariants.violations(self.st, self.totals), [])

    def assert_caught(self, prefix: str) -> None:
        v = invariants.violations(self.st, self.totals)
        self.assertTrue(any(x.startswith(prefix) for x in v), v)
        with self.assertRaises(invariants.InvariantError):
            invariants.check(self.st, self.totals)

    def test_conservation(self) -> None:
        self.st.players[0].hand[Resource.ORE] += 1
        self.assert_caught("conservation.ore")

    def test_pieces(self) -> None:
        self.st.players[1].pieces_left[BuildKind.ROAD] += 1
        self.assert_caught("pieces.1.road")

    def test_distance_rule(self) -> None:
        v = next(iter(self.st.buildings))
        n = self.st.board.board.vertex_neighbors[v][0]
        self.st.buildings[n] = Building(self.st.buildings[v].seat, BuildKind.SETTLEMENT)
        self.st.player(self.st.buildings[v].seat).pieces_left[BuildKind.SETTLEMENT] -= 1
        self.assert_caught("distance_rule")

    def test_points(self) -> None:
        self.st.players[2].points += 1
        self.assert_caught("points.2")

    def test_unconnected_road(self) -> None:
        seat = 0
        far = next(e for e in self.st.board.board.land_edges
                   if e not in self.st.roads and not any(
                       w in self.st.buildings or any(x in self.st.roads for x in self.st.board.board.vertex_edges[w])
                       for w in self.st.board.board.edge_vertices[e]))
        self.st.roads[far] = seat
        self.st.players[seat].pieces_left[BuildKind.ROAD] -= 1
        self.assert_caught("road.unconnected.0")


if __name__ == "__main__":
    unittest.main()
