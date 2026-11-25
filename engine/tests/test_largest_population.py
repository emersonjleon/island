"""Largest Population: the player with the most settlers, in every game where settlers stay."""
from __future__ import annotations

import unittest

from engine import codec, game, views
from engine.events import LargestPopulation, Points
from engine.rules import largest_population
from engine.state import GameState, Settler
from engine.tests.test_dice import make_state, place, set_hand


def new_state(overrides: dict | None = None) -> GameState:
    merged = {"settlers": {"leave_after_setup": False, "largest_population": {"min": 2}}}
    for k, v in (overrides or {}).items():
        merged[k] = {**merged.get(k, {}), **v}
    return make_state(n=3, overrides=merged, stage=3, clock=False)


def add_settlers(state: GameState, seat: int, n: int) -> None:
    vertex = state.settlers[state.player(seat).settler_ids[0]].vertex
    for _ in range(n):
        sid = state.next_id("settler")
        state.settlers[sid] = Settler(id=sid, seat=seat, vertex=vertex)
        state.player(seat).settler_ids.append(sid)


def step(state: GameState) -> list:
    return largest_population.update_population(state, state.now_ms)


class LargestPopulationTest(unittest.TestCase):
    def test_most_settlers_wins_the_award_and_a_tie_keeps_it(self) -> None:
        s = new_state()
        base = {p.seat: largest_population.population(s, p.seat) for p in s.players}
        self.assertEqual(set(base.values()), {1})
        step(s)
        self.assertIsNone(largest_population.holder(s))
        p0 = s.players[0].points
        add_settlers(s, 0, 1)                                   # 2 settlers: the minimum
        events = step(s)
        self.assertEqual(largest_population.holder(s), 0)
        self.assertEqual(s.players[0].points, p0 + 2)
        self.assertEqual([type(e) for e in events], [LargestPopulation, Points])
        add_settlers(s, 1, 1)                                   # a tie keeps the holder
        step(s)
        self.assertEqual(largest_population.holder(s), 0)
        p1 = s.players[1].points
        add_settlers(s, 1, 1)                                   # 3 beats 2
        step(s)
        self.assertEqual(largest_population.holder(s), 1)
        self.assertEqual((s.players[0].points, s.players[1].points), (p0, p1 + 2))
        self.assertEqual(views.project_state(s, 2)["largest_population"]["holder"], 1)
        self.assertEqual(step(s), [])                           # nothing changed

    def test_with_or_without_ages(self) -> None:
        for ages in (False, True):
            with self.subTest(ages=ages):
                s = new_state({"ages": {"enabled": ages}})
                add_settlers(s, 2, 2)
                step(s)
                self.assertEqual(largest_population.holder(s), 2)

    def test_not_played_when_settlers_leave(self) -> None:
        s = make_state(n=3, overrides={"settlers": {"largest_population": {"min": 1}}}, stage=3, clock=False)
        self.assertTrue(s.settings.settlers.leave_after_setup)
        self.assertEqual(step(s), [])
        self.assertIsNone(largest_population.holder(s))
        self.assertEqual(views.project_state(s, 0)["largest_population"], {})

    def test_buying_a_settler_can_win_the_award(self) -> None:
        s = new_state({"settlers": {"per_settlement": 0, "per_city": 0}})
        s.players[0].setup_done = True
        place(s, 0, 5)
        set_hand(s, 0, **{r.value: n for r, n in s.settings.economy.costs.settler.items()})
        events = game.apply(s, 0, {"a": "buy_settler"}, s.now_ms)
        self.assertIn(LargestPopulation, [type(e) for e in events])
        self.assertEqual(largest_population.holder(s), 0)

    def test_old_snapshots_and_overrides_load(self) -> None:
        s = new_state()
        d = codec.dump(s)
        d["settings"]["schema_version"] = 1
        d["settings"].pop("settlers")["largest_population"] = None
        d["settings"]["settlers"] = {k: v for k, v in s.settings.settlers.model_dump(mode="json").items()
                                     if k != "largest_population"}
        d["settings"]["ages"]["largest_population"] = {"points": 4, "min": 6, "per_settlement": 1,
                                                       "per_city": 2, "per_megacity": 4}
        restored = codec.load(d)
        self.assertEqual(restored.settings.settlers.largest_population.points, 4)
        from engine.settings import load_preset
        loaded = load_preset("settlers", {"ages": {"largest_population": {"points": 3, "min": 6}}},
                             implemented_stage=3)
        self.assertEqual(loaded.settlers.largest_population.points, 3)


if __name__ == "__main__":
    unittest.main()
