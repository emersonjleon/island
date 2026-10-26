"""Megacities: an upgrade of an own city that produces more and scores more."""
import unittest

from engine import game
from engine.errors import RuleError
from engine.rules import placement, production
from engine.settings import parse_settings
from engine.settings.enums import BuildKind, Resource
from engine.state import Building, GameState
from engine.tests.fixtures import make_seats, standard_board
from engine.tests.test_placement import act, bcmd, give, inner_vertices, setup_player

M, C, S = BuildKind.MEGACITY, BuildKind.CITY, BuildKind.SETTLEMENT
SLOW = {"clock": {"roll_interval_ms": 120000}}


def ready(overrides: dict | None = None) -> tuple[GameState, int, int]:  # type: ignore[type-arg]
    settings = parse_settings({**SLOW, **(overrides or {})})
    state, _ = game.new_game(settings, make_seats(2), 1, board=standard_board())
    now = setup_player(state, 0, 0)
    now = setup_player(state, 1, now)
    v = next(v for v, b in sorted(state.buildings.items()) if b.seat == 0)
    return state, v, now


def upgrade(state: GameState, seat: int, v: int, kind: BuildKind, now: int) -> int:
    give(state, seat, placement.cost_of(state, kind))
    act(state, seat, bcmd(kind, v), now)
    now += getattr(state.settings.build.time_ms, kind.value)
    game.advance(state, now)
    return now


class MegacityTest(unittest.TestCase):
    def test_needs_own_city(self) -> None:
        state, v, now = ready()
        give(state, 0, placement.cost_of(state, M))
        game.advance(state, now)
        with self.assertRaises(RuleError) as cm:
            game.apply(state, 0, bcmd(M, v), now)
        self.assertEqual(cm.exception.code, "build.not_own_city")
        other = next(x for x, b in state.buildings.items() if b.seat == 1)
        state.buildings[other] = Building(1, C)
        with self.assertRaises(RuleError) as cm:
            game.apply(state, 0, bcmd(M, other), now)
        self.assertEqual(cm.exception.code, "build.not_own_city")

    def test_upgrade_points_pieces_and_buildable(self) -> None:
        state, v, now = ready()
        p = state.player(0)
        now = upgrade(state, 0, v, C, now)
        self.assertEqual(p.points, 3)
        cities_left = p.pieces_left[C]
        give(state, 0, placement.cost_of(state, M))
        self.assertIn(v, placement.buildable(state, 0)["megacities"])
        state.player(0).hand = {r: 0 for r in Resource}
        give(state, 0, placement.cost_of(state, M))
        act(state, 0, bcmd(M, v), now)
        self.assertEqual(state.buildings[v].kind, C)          # still a city while building
        now += state.settings.build.time_ms.megacity
        game.advance(state, now)
        self.assertEqual(state.buildings[v].kind, M)
        self.assertEqual(p.points, 4)                         # settlement 1 + megacity 3
        self.assertEqual(p.pieces_left[C], cities_left + 1)   # the city piece comes back
        self.assertEqual(p.pieces_left[M], state.settings.pieces.megacities - 1)

    def test_produces_four(self) -> None:
        state, v, now = ready()
        now = upgrade(state, 0, v, C, now)
        now = upgrade(state, 0, v, M, now)
        hexes = [h for h in state.board.board.vertex_hexes[v] if state.board.hex_resource(h) is not None]
        h = hexes[0]
        owed, _ = production.owed_by_resource(state, state.board.token[h])
        res = state.board.hex_resource(h)
        assert res is not None
        same = sum(1 for x in hexes if state.board.token[x] == state.board.token[h]
                   and state.board.hex_resource(x) == res)
        self.assertGreaterEqual(owed[res][0], 4 * same)

    def test_disabled_with_zero_pieces(self) -> None:
        state, v, now = ready({"pieces": {"megacities": 0}})
        now = upgrade(state, 0, v, C, now)
        give(state, 0, placement.cost_of(state, M))
        game.advance(state, now)
        with self.assertRaises(RuleError) as cm:
            game.apply(state, 0, bcmd(M, v), now)
        self.assertEqual(cm.exception.code, "build.no_piece")
        self.assertEqual(placement.buildable(state, 0)["megacities"], [])

    def test_not_during_setup(self) -> None:
        state, _ = game.new_game(parse_settings(SLOW), make_seats(2), 1, board=standard_board())
        v = inner_vertices(state)[0]
        state.buildings[v] = Building(0, C)
        self.assertEqual(placement.build_error(state, 0, M, v).code, "build.setup_unfinished")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
