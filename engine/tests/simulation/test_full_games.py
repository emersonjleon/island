"""Full games played by bots under a manual clock (WP8).

Invariants (resource and piece conservation, distance rule, road connectivity,
cached points, timers) are checked after every step by the runner.
"""
import unittest

from engine.settings import load_preset, parse_settings
from engine.sim.runner import run_game
from engine.tests.fixtures import make_seats, make_settings, standard_board

HOURS = 3600 * 1000
MAX_MS = 4 * HOURS


class GreedyGamesTest(unittest.TestCase):
    def assert_won(self, r, target: int) -> None:  # type: ignore[no-untyped-def]
        st = r.state
        self.assertTrue(r.finished, f"no winner after {st.now_ms} ms, points {[p.points for p in st.players]}")
        self.assertIsNotNone(st.winner)
        self.assertGreaterEqual(st.players[st.winner].points, target)
        self.assertEqual(st.finished_at, st.now_ms)
        self.assertIsNone(st.timers.get(st.roll_timer_id))

    def test_player_counts_on_generated_boards(self) -> None:
        for players in (2, 3, 4):
            for seed in range(3):
                with self.subTest(players=players, seed=seed):
                    r = run_game(make_settings(), make_seats(players), seed, ["greedy"] * players, MAX_MS)
                    self.assert_won(r, 10)
                    # a game lasts a sensible number of rolls
                    self.assertTrue(20 <= r.rolls <= 600, r.rolls)

    def test_fixed_board(self) -> None:
        r = run_game(make_settings(), make_seats(3), 7, ["greedy"] * 3, MAX_MS, board=standard_board())
        self.assert_won(r, 10)

    def test_board_sizes(self) -> None:
        for n in (12, 37, 61):
            for players in (2, 4):
                with self.subTest(land=n, players=players):
                    s = parse_settings({"board": {"land_hexes": n}})
                    self.assert_won(run_game(s, make_seats(players), 0, ["greedy"] * players, MAX_MS), 10)

    def test_blitz_preset(self) -> None:
        s = load_preset("blitz")
        r = run_game(s, make_seats(3), 3, ["greedy"] * 3, MAX_MS)
        self.assert_won(r, s.victory.target)

    def test_variant_settings(self) -> None:
        variants = [
            {"build": {"network_builds_timed": False}},
            {"build": {"refund_pct": 50}},
            {"robber": {"require_adjacent": True, "steal_pct": 100}},
            {"economy": {"starting_materials_from_bank": False}},
            {"trading": {"harbor_trade": False}},
        ]
        for i, ov in enumerate(variants):
            with self.subTest(overrides=ov):
                r = run_game(parse_settings(ov), make_seats(3), 10 + i, ["greedy"] * 3, MAX_MS)
                self.assert_won(r, 10)


class RandomGamesTest(unittest.TestCase):
    """Random bots explore odd move orders; games may stall (board or pieces full),
    but no step may break an invariant or raise."""

    def test_random_and_mixed(self) -> None:
        mixes = (["random", "random"], ["random"] * 3, ["greedy", "random", "random", "greedy"])
        finished = 0
        for mix in mixes:
            for seed in range(3):
                with self.subTest(mix=mix, seed=seed):
                    r = run_game(make_settings(), make_seats(len(mix)), 100 + seed, mix, 2 * HOURS)
                    finished += r.finished
                    self.assertGreater(len(r.log), 0)
        self.assertGreaterEqual(finished, 5)

    def test_small_board_crowded(self) -> None:
        s = parse_settings({"board": {"land_hexes": 7}})
        r = run_game(s, make_seats(4), 1, ["random"] * 4, HOURS)
        self.assertGreater(r.steps, 0)


if __name__ == "__main__":
    unittest.main()
