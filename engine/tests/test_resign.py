"""Resigning (engine.rules.resign) and game statistics (engine.rules.stats)."""
from __future__ import annotations

import unittest

from engine import codec, game, views
from engine.errors import RuleError
from engine.events import Event, GameOver, Produced, Resigned
from engine.rules import victory
from engine.settings.enums import ProductionLog, Resource, ScoreVisibility
from engine.sim import invariants
from engine.sim.bots import make_bot
from engine.sim.runner import Simulation
from engine.state import SeatInfo
from engine.tests.fixtures import make_seats, make_settings, standard_board

SEED = 7


def running_sim(seats: list[SeatInfo] | None = None, rolls: int = 12) -> tuple[Simulation, list[Event]]:
    seats = seats or make_seats(3)
    seen: list[Event] = []
    sim = Simulation(make_settings(), seats, SEED, [make_bot("greedy", i, SEED * 100 + i) for i in range(len(seats))],
                     board=standard_board(), on_events=seen.extend)
    while len(sim.state.dice_history) < rolls and not sim.state.finished:
        sim.step()
    assert not sim.state.finished, "the test game ended too early"
    return sim, seen


def resign(sim: Simulation, seat: int) -> list[Event]:
    events = game.apply(sim.state, seat, {"a": "resign"}, sim.state.now_ms)
    sim._emit(events)            # keeps the simulation's invariant checks running
    return events


class ResignTest(unittest.TestCase):
    def test_resign_returns_hand_and_keeps_pieces(self) -> None:
        sim, _ = running_sim()
        st = sim.state
        p = st.players[1]
        buildings = {v: b.seat for v, b in st.buildings.items()}
        roads = dict(st.roads)
        points = p.points
        events = resign(sim, 1)
        self.assertTrue(p.resigned)
        self.assertEqual(p.resigned_at, st.now_ms)
        self.assertEqual(p.hand_count, 0)
        self.assertEqual(p.settler_ids, [])
        self.assertFalse(any(c.seat == 1 for c in st.constructions.values()))
        self.assertEqual({v: b.seat for v, b in st.buildings.items() if v in buildings}, buildings)
        self.assertEqual({e: s for e, s in st.roads.items() if e in roads}, roads)
        self.assertEqual(p.points, points)
        self.assertIsInstance([e for e in events if isinstance(e, Resigned)][0], Resigned)
        self.assertEqual(st.phase, "running")
        self.assertEqual(invariants.violations(st, sim.totals), [])

    def test_resigned_player_cannot_act_or_win(self) -> None:
        sim, _ = running_sim()
        resign(sim, 1)
        with self.assertRaises(RuleError) as ctx:
            game.apply(sim.state, 1, {"a": "buy_dev_card"}, sim.state.now_ms)
        self.assertEqual(ctx.exception.code, "game.resigned")
        with self.assertRaises(RuleError):
            game.apply(sim.state, 1, {"a": "resign"}, sim.state.now_ms)
        sim.state.players[1].points = sim.state.settings.victory.target + 3
        game.advance(sim.state, sim.state.now_ms + 1)
        self.assertIsNone(victory.leader_at_target(sim.state))

    def test_resigned_buildings_produce_nothing(self) -> None:
        sim, seen = running_sim()
        resign(sim, 1)
        start = len(seen)
        rolls = len(sim.state.dice_history)
        while len(sim.state.dice_history) < rolls + 15 and not sim.state.finished:
            sim.step()
        for ev in seen[start:]:
            if isinstance(ev, Produced):
                self.assertNotIn(1, ev.gains)
        self.assertEqual(sim.state.players[1].hand_count, 0)

    def test_last_player_standing_wins(self) -> None:
        sim, _ = running_sim()
        resign(sim, 0)
        events = resign(sim, 2)
        st = sim.state
        self.assertEqual(st.phase, "finished")
        self.assertEqual(st.winner, 1)
        over = [e for e in events if isinstance(e, GameOver)]
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0].reason, "resign")
        self.assertEqual(over[0].winner, 1)

    def test_game_ends_when_only_computer_players_are_left(self) -> None:
        seats = make_seats(3)
        seats[1].user_id = None
        seats[2].user_id = None
        sim, _ = running_sim(seats)
        st = sim.state
        events = resign(sim, 0)
        self.assertEqual(st.phase, "finished")
        leader = max((p for p in st.players if p.seat != 0), key=lambda p: (p.points, -p.seat))
        self.assertEqual(st.winner, leader.seat)
        self.assertEqual([e.reason for e in events if isinstance(e, GameOver)], ["resign"])

    def test_bots_only_game_keeps_going_after_one_resigns(self) -> None:
        seats = [SeatInfo(seat=i, user_id=None, name=f"b{i}", colour=s.colour) for i, s in enumerate(make_seats(3))]
        sim, _ = running_sim(seats)
        resign(sim, 2)
        self.assertEqual(sim.state.phase, "running")

    def test_resign_survives_a_snapshot(self) -> None:
        sim, _ = running_sim()
        resign(sim, 2)
        st = codec.load(codec.dump(sim.state))
        self.assertTrue(st.players[2].resigned)
        self.assertEqual(st.players[2].resigned_at, sim.state.players[2].resigned_at)
        old = codec.dump(sim.state)
        for p in old["players"]:
            del p["resigned_at"]                    # a snapshot from before this change
        self.assertFalse(any(p.resigned for p in codec.load(old).players))

    def test_view_marks_resigned(self) -> None:
        sim, _ = running_sim()
        resign(sim, 2)
        view = views.project_state(sim.state, 0)
        self.assertEqual([p["resigned"] for p in view["players"]], [False, False, True])


class StatsTest(unittest.TestCase):
    def test_timeline_follows_points_and_production_adds_up(self) -> None:
        sim, seen = running_sim(rolls=30)
        st = sim.state
        tl = st.ext["stats"]["timeline"]
        for p in st.players:
            entries = tl[str(p.seat)]
            self.assertEqual(entries[0], [0, 0])
            self.assertEqual(entries[-1][1], p.points)
            times = [t for t, _ in entries]
            self.assertEqual(times, sorted(times))
        totals: dict[str, dict[str, int]] = {}
        for ev in seen:
            if isinstance(ev, Produced):
                for seat, gains in ev.gains.items():
                    for r, n in gains.items():
                        mine = totals.setdefault(str(seat), {})
                        mine[Resource(r).value] = mine.get(Resource(r).value, 0) + n
        self.assertEqual(st.ext["stats"]["produced"], totals)
        self.assertTrue(totals)

    def test_view_hides_what_the_settings_hide(self) -> None:
        sim, _ = running_sim()
        st = sim.state
        self.assertEqual(set(views.project_state(st, 0)["stats"]["timeline"]), {"0", "1", "2"})
        hidden = st.settings.model_copy(update={"visibility": st.settings.visibility.model_copy(
            update={"scores": ScoreVisibility.HIDDEN_UNTIL_END, "production_log": ProductionLog.OWN})})
        st.settings = hidden
        stats = views.project_state(st, 0)["stats"]
        self.assertEqual(set(stats["timeline"]), {"0"})
        self.assertEqual(set(stats["produced"]) - {"0"}, set())
        self.assertEqual(views.project_state(st, None)["stats"], {"timeline": {}, "produced": {}})


if __name__ == "__main__":
    unittest.main()
