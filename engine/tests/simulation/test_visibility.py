"""Redaction over whole simulated games (WP8): private hand data never reaches others.

By design (classic rules) production, bank trades and build costs are public
facts; what must stay private under ``visibility.hands = counts`` are the
contents of a hand: ``hand``, ``robber_stole.lost``, ``starting_resources.gained``,
``starting_materials.materials`` and the private ``buildable`` sets.
"""
import json
import unittest

from engine import views
from engine.sim.bots import make_bot
from engine.sim.runner import Simulation
from engine.tests.fixtures import make_seats, make_settings

PRIVATE_MAPS = {"hand": "hand", "robber_stole": "lost", "starting_resources": "gained",
                "starting_materials": "materials"}


def play(overrides: dict, seed: int = 4) -> tuple[Simulation, list]:  # type: ignore[type-arg]
    batches: list = []
    sim = Simulation(make_settings(overrides), make_seats(3), seed,
                     [make_bot("greedy", i, i) for i in range(3)], on_events=batches.append)
    sim.run(3600 * 1000)
    return sim, batches


class VisibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.counts = play({})
        cls.hidden = play({"visibility": {"hands": "hidden"}})
        cls.open = play({"visibility": {"hands": "open"}})

    def _check(self, sim: Simulation, batches: list, mode: str) -> None:  # type: ignore[type-arg]
        seen_private = 0
        for batch in batches:
            for viewer in (0, 1, 2, None):
                out = views.filter_events(batch, viewer, sim.state)
                json.dumps(out)
                for d in out:
                    k = d["k"]
                    own = viewer is not None and d.get("seat") == viewer
                    if k == "buildable":
                        self.assertTrue(own, "buildable leaked")
                    if k in PRIVATE_MAPS and not own:
                        seen_private += 1
                        field = PRIVATE_MAPS[k]
                        self.assertNotEqual(mode, "hidden", f"{k} sent with hands=hidden")
                        if mode == "counts":
                            self.assertNotIn(field, d)
                            self.assertIsInstance(d[f"{field}_count"], int)
                        else:
                            self.assertIn(field, d)
        if mode != "hidden":
            self.assertGreater(seen_private, 0)

    def test_counts(self) -> None:
        self._check(*self.counts, "counts")

    def test_hidden(self) -> None:
        self._check(*self.hidden, "hidden")

    def test_open(self) -> None:
        self._check(*self.open, "open")

    def test_redacted_counts_match_hands(self) -> None:
        sim, batches = self.counts
        last_count: dict[int, int] = {}
        for batch in batches:
            for d in views.filter_events(batch, None, sim.state):
                if d["k"] == "hand":
                    last_count[d["seat"]] = d["hand_count"]
        for p in sim.state.players:
            if p.seat in last_count:
                self.assertEqual(last_count[p.seat], p.hand_count)

    def test_project_state(self) -> None:
        for (sim, _), mode in ((self.counts, "counts"), (self.hidden, "hidden"), (self.open, "open")):
            for viewer in (0, 1, 2, None):
                v = views.project_state(sim.state, viewer)
                json.dumps(v)
                for p in v["players"]:
                    own = p["seat"] == viewer
                    self.assertEqual("hand" in p, own or mode == "open")
                    self.assertEqual("hand_count" in p, own or mode != "hidden")
                self.assertEqual("buildable" in v, viewer is not None)


if __name__ == "__main__":
    unittest.main()
