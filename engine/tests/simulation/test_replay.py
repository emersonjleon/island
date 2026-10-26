"""Determinism and persistence: replaying the command log, snapshot + replay (WP8)."""
import json
import unittest

from engine import codec
from engine.sim.bots import make_bot
from engine.sim.runner import CommandRecord, Simulation, replay, resume, run_game
from engine.tests.fixtures import make_seats, make_settings

MAX_MS = 4 * 3600 * 1000


def _json_round(d):  # type: ignore[no-untyped-def]
    return json.loads(json.dumps(d))


class ReplayTest(unittest.TestCase):
    def test_same_seed_same_game(self) -> None:
        a = run_game(make_settings(), make_seats(3), 21, ["greedy", "random", "greedy"], MAX_MS)
        b = run_game(make_settings(), make_seats(3), 21, ["greedy", "random", "greedy"], MAX_MS)
        self.assertEqual(codec.state_hash(a.state), codec.state_hash(b.state))
        self.assertEqual(a.log, b.log)

    def test_replay_log_reproduces_final_state(self) -> None:
        for seed, mix in ((1, ["greedy"] * 3), (2, ["random", "greedy"]), (3, ["random"] * 4)):
            with self.subTest(seed=seed):
                r = run_game(make_settings(), make_seats(len(mix)), seed, mix, MAX_MS // 4)
                log = [CommandRecord(**_json_round(c.to_dict())) for c in r.log]
                st = replay(make_settings(), make_seats(len(mix)), seed, log, until_ms=r.state.now_ms)
                self.assertEqual(codec.state_hash(st), codec.state_hash(r.state))

    def test_snapshot_then_replay(self) -> None:
        """Kill mid-game: restore the snapshot, replay later commands, reach the same end."""
        settings, seats, seed = make_settings(), make_seats(3), 5
        snaps: list[tuple[dict, int]] = []
        bots = [make_bot("greedy", i, 50 + i) for i in range(3)]
        sim = Simulation(settings, seats, seed, bots)
        while not sim.state.finished and sim.state.now_ms < MAX_MS:
            sim.step()
            if sim.steps % 97 == 0:
                snaps.append((_json_round(codec.dump(sim.state)), len(sim.log)))
        self.assertTrue(sim.state.finished)
        self.assertGreater(len(snaps), 5)
        final = codec.state_hash(sim.state)
        for snap, n in snaps[:: max(1, len(snaps) // 6)]:
            with self.subTest(at=snap["now_ms"]):
                restored = codec.load(snap)
                self.assertEqual(codec.state_hash(restored), codec.state_hash(codec.load(snap)))
                st = resume(snap, sim.log[n:], until_ms=sim.state.now_ms)
                self.assertEqual(codec.state_hash(st), final)

    def test_dump_load_mid_game_continues_identically(self) -> None:
        """A loaded copy driven by the same bots stays identical to the original."""
        settings, seats = make_settings(), make_seats(2)
        a = Simulation(settings, seats, 9, [make_bot("greedy", i, i) for i in range(2)])
        for _ in range(300):
            a.step()
        b = Simulation(settings, seats, 9, [make_bot("greedy", i, i) for i in range(2)])
        for _ in range(300):
            b.step()
        b.state = codec.load(_json_round(codec.dump(b.state)))
        for _ in range(300):
            a.step()
            b.step()
        self.assertEqual(codec.state_hash(a.state), codec.state_hash(b.state))


if __name__ == "__main__":
    unittest.main()
