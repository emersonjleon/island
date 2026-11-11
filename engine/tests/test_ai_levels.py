"""Computer players: every level finishes games legally, and harder levels win more."""
import unittest
from collections import Counter

from engine import codec
from engine.ai.driver import BotDriver
from engine.ai.levels import DEFAULT_LEVEL, LEVEL_NAMES, LEVELS, make_level_bot
from engine.sim.runner import Simulation, replay
from engine.tests.fixtures import make_seats, make_settings

MAX_MS = 4 * 3600 * 1000
TICK_MS = 200


class Paced:
    """Adapter so the simulation runner calls each bot at its level's pace (via BotDriver)."""

    def __init__(self, driver: BotDriver, bot) -> None:  # type: ignore[no-untyped-def]
        self.driver, self.bot, self.seat = driver, bot, bot.seat

    def decide(self, state):  # type: ignore[no-untyped-def]
        if self.driver.next_ms[self.seat] > state.now_ms:
            return []
        self.driver.next_ms[self.seat] = state.now_ms + self.bot.level.think_ms
        return self.bot.decide(state)


def play(levels: list[str], seed: int, check: bool = False):  # type: ignore[no-untyped-def]
    bots = [make_level_bot(lv, i, seed * 10 + i) for i, lv in enumerate(levels)]
    driver = BotDriver(bots)
    sim = Simulation(make_settings(), make_seats(len(levels)), seed, [Paced(driver, b) for b in bots],
                     think_ms=TICK_MS, check=check)
    return sim.run(MAX_MS)


def wins(levels: list[str], seeds: range) -> Counter:
    """Winner level per game; the seating rotates so no level always sits first."""
    out: Counter = Counter()
    for seed in seeds:
        k = seed % len(levels)
        order = levels[k:] + levels[:k]
        r = play(order, seed)
        out[order[r.state.winner] if r.state.winner is not None else None] += 1
    return out


class LevelTableTest(unittest.TestCase):
    def test_levels(self) -> None:
        self.assertEqual(LEVEL_NAMES, ("easy", "medium", "hard"))
        self.assertIn(DEFAULT_LEVEL, LEVELS)
        think = [LEVELS[n].think_ms for n in LEVEL_NAMES]
        self.assertEqual(think, sorted(think, reverse=True), "harder bots think faster")
        mistakes = [LEVELS[n].mistake_pct for n in LEVEL_NAMES]
        self.assertEqual(mistakes, sorted(mistakes, reverse=True))

    def test_driver_staggers_and_reschedules(self) -> None:
        bots = [make_level_bot("easy", s, s) for s in range(4)]
        d = BotDriver(bots, start_ms=1000)
        self.assertEqual(sorted(d.next_ms.values()), [1000, 2000, 3000, 4000])
        self.assertEqual(d.next_wakeup(), 1000)
        self.assertEqual([b.seat for b in d.due(2000)], [0, 1])
        self.assertEqual(d.next_ms[0], 2000 + LEVELS["easy"].think_ms)
        self.assertEqual(d.due(2000), [])
        self.assertFalse(BotDriver([]))
        self.assertIsNone(BotDriver([]).next_wakeup())


class LevelGamesTest(unittest.TestCase):
    def test_every_level_finishes_with_invariants(self) -> None:
        for level in LEVEL_NAMES:
            with self.subTest(level=level):
                r = play([level] * 3, 5, check=True)
                self.assertTrue(r.finished, [p.points for p in r.state.players])

    def test_bot_games_replay_from_the_log(self) -> None:
        r = play(["easy", "medium", "hard"], 11)
        again = replay(make_settings(), make_seats(3), 11, r.log, until_ms=r.state.now_ms)
        self.assertEqual(codec.state_hash(again), codec.state_hash(r.state))

    def test_harder_levels_win_more(self) -> None:
        seeds = range(20)
        vs_easy = wins(["easy", "medium"], seeds)
        self.assertGreaterEqual(vs_easy["medium"], 14, vs_easy)
        hard_easy = wins(["easy", "hard"], seeds)
        self.assertGreaterEqual(hard_easy["hard"], 14, hard_easy)
        hard_medium = wins(["medium", "hard"], range(30))
        self.assertGreater(hard_medium["hard"], hard_medium["medium"], hard_medium)


if __name__ == "__main__":
    unittest.main()
