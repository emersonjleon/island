import json
import unittest

from engine import game, views
from engine.events import (
    Buildable, Built, DiceRolled, Hand, Produced, RobberStole, StartingMaterials, StartingResources,
)
from engine.settings import parse_settings
from engine.settings.enums import BuildKind, Resource
from engine.state import Building, Construction, GameState, Settler, SettlerStep
from engine.tests.fixtures import make_seats, make_settings, standard_board

R = Resource


def make_state(overrides: dict | None = None, settings=None) -> GameState:  # type: ignore[no-untyped-def]
    with game.temporary_registry(empty=True):
        state, _ = game.new_game(settings or make_settings(overrides), make_seats(3), 1, board=standard_board())
    state.players[0].hand[R.LUMBER] = 2
    state.players[0].hand[R.ORE] = 1
    state.players[1].hand[R.WOOL] = 4
    state.players[1].points = 3
    state.buildings[10] = Building(1, BuildKind.SETTLEMENT)
    state.roads[12] = 1
    state.settlers[1] = Settler(id=1, seat=0, vertex=3, path=[5],
                                step=SettlerStep(edge=4, from_v=3, to_v=4, t0=100, t1=1600), timer_id=1)
    state.constructions[1] = Construction(id=1, seat=1, kind=BuildKind.ROAD, target=13, builder=None,
                                          paid={R.BRICK: 1, R.LUMBER: 1}, started_ms=0, done_ms=3000)
    return state


EVENTS = [
    DiceRolled(at=1, dice=[3, 4], sum=7, next_roll_at=21),
    RobberStole(at=1, seat=1, lost={R.WOOL: 2}),
    Hand(at=1, seat=1, hand={R.WOOL: 2}),
    Buildable(at=1, seat=1, roads=[1], settlements=[], cities=[]),
    StartingMaterials(at=0, seat=1, materials={R.BRICK: 4, R.LUMBER: 4}),
    StartingResources(at=5, seat=1, gained={R.ORE: 1, R.FISH: 1}),
    Built(at=5, seat=1, kind=BuildKind.SETTLEMENT, target=10, points_after=1),
]


class ProjectStateTest(unittest.TestCase):
    def tearDown(self) -> None:
        views.register_buildable_provider(None)

    def test_counts(self) -> None:
        s = make_state()
        v = views.project_state(s, 0)
        json.dumps(v)
        p0, p1 = v["players"][0], v["players"][1]
        self.assertEqual(p0["hand"], {"lumber": 2, "brick": 0, "wool": 0, "grain": 0, "ore": 1, "fish": 0})
        self.assertEqual(p0["hand_count"], 3)
        self.assertNotIn("hand", p1)
        self.assertEqual(p1["hand_count"], 4)
        self.assertEqual(p1["points"], 3)
        spect = views.project_state(s, None)
        self.assertTrue(all("hand" not in p and "hand_count" in p for p in spect["players"]))
        self.assertEqual(v["buildings"], [{"vertex": 10, "seat": 1, "kind": "settlement"}])
        self.assertEqual(v["roads"], [{"edge": 12, "seat": 1}])
        self.assertEqual(v["settlers"][0]["step"], {"edge": 4, "from_v": 3, "to_v": 4, "t0": 100, "t1": 1600})
        self.assertEqual(v["constructions"][0]["t1"], 3000)
        self.assertEqual(v["robber"], 9)
        self.assertEqual(v["bank"]["ore"], 19)
        self.assertEqual(v["phase"], "setup")
        self.assertEqual(p0["setup"]["remaining"], {"settlement": 2, "road": 2})
        self.assertEqual(p0["pieces"], {"road": 15, "settlement": 5, "city": 4})

    def test_open_and_hidden(self) -> None:
        v = views.project_state(make_state({"visibility": {"hands": "open"}}), None)
        self.assertEqual(v["players"][1]["hand"]["wool"], 4)
        s = make_state({"visibility": {"hands": "hidden"}})
        v = views.project_state(s, 0)
        self.assertIn("hand", v["players"][0])
        self.assertNotIn("hand", v["players"][1])
        self.assertNotIn("hand_count", v["players"][1])

    def test_scores_hidden_until_end(self) -> None:
        settings = parse_settings({"visibility": {"scores": "hidden_until_end"}}, implemented_stage=3)
        s = make_state(settings=settings)
        v = views.project_state(s, 0)
        self.assertNotIn("points", v["players"][1])
        self.assertIn("points", v["players"][0])
        s.phase = "finished"
        self.assertEqual(views.project_state(s, 0)["players"][1]["points"], 3)

    def test_buildable(self) -> None:
        s = make_state()
        s.buildable_cache[0] = {"roads": [7], "settlements": [], "cities": []}
        self.assertEqual(views.project_state(s, 0)["buildable"]["roads"], [7])
        self.assertNotIn("buildable", views.project_state(s, 1))
        self.assertNotIn("buildable", views.project_state(s, None))
        views.register_buildable_provider(lambda st, seat: {"roads": [seat], "settlements": [], "cities": []})
        self.assertEqual(views.project_state(s, 2)["buildable"]["roads"], [2])
        self.assertNotIn("buildable", views.project_state(s, None))


class FilterEventsTest(unittest.TestCase):
    def kinds(self, out: list[dict]) -> list[str]:
        return [d["k"] for d in out]

    def test_owner_sees_everything(self) -> None:
        s = make_state()
        out = views.filter_events(EVENTS, 1, s)
        self.assertEqual(out, [e.model_dump(mode="json") for e in EVENTS])

    def test_counts_redaction(self) -> None:
        s = make_state()
        for viewer in (0, None):
            out = views.filter_events(EVENTS, viewer, s)
            json.dumps(out)
            self.assertEqual(self.kinds(out), ["dice_rolled", "robber_stole", "hand", "starting_materials",
                                               "starting_resources", "built"])
            text = json.dumps(out)
            for res in ("wool", "brick", "ore", "fish"):
                self.assertNotIn(res, text)
            self.assertEqual(out[1], {"k": "robber_stole", "at": 1, "seat": 1, "lost_count": 2})
            self.assertEqual(out[2], {"k": "hand", "at": 1, "seat": 1, "hand_count": 2})
            self.assertEqual(out[3]["materials_count"], 8)
            self.assertEqual(out[4]["gained_count"], 2)

    def test_default_visibility_without_state(self) -> None:
        out = views.filter_events(EVENTS, 0)
        self.assertEqual(out[1], {"k": "robber_stole", "at": 1, "seat": 1, "lost_count": 2})

    def test_open(self) -> None:
        s = make_state({"visibility": {"hands": "open"}})
        out = views.filter_events(EVENTS, 0, s)
        self.assertEqual(self.kinds(out), ["dice_rolled", "robber_stole", "hand", "starting_materials",
                                           "starting_resources", "built"])
        self.assertEqual(out[1]["lost"], {"wool": 2})

    def test_hidden(self) -> None:
        s = make_state({"visibility": {"hands": "hidden"}})
        self.assertEqual(self.kinds(views.filter_events(EVENTS, None, s)), ["dice_rolled", "built"])
        self.assertEqual(len(views.filter_events(EVENTS, 1, s)), len(EVENTS))

    def test_production_log(self) -> None:
        ev = [Produced(at=3, roll=8, gains={0: {R.GRAIN: 1}, 2: {R.ORE: 2}}, skipped={R.WOOL: "bank_shortage"})]
        s = make_state()
        self.assertEqual(views.filter_events(ev, None, s)[0]["gains"], {"0": {"grain": 1}, "2": {"ore": 2}})
        s = make_state({"visibility": {"production_log": "own"}})
        self.assertEqual(views.filter_events(ev, 2, s)[0]["gains"], {"2": {"ore": 2}})
        self.assertEqual(views.filter_events(ev, None, s)[0]["gains"], {})
        self.assertEqual(views.filter_events(ev, 1, s)[0]["skipped"], {"wool": "bank_shortage"})



class EventModelTest(unittest.TestCase):
    def test_round_trip_and_schema(self) -> None:
        from engine.events import EVENT_TYPES, event_json_schema, parse_event
        for e in EVENTS:
            self.assertEqual(parse_event(json.loads(json.dumps(e.to_dict()))), e)
        for k, cls in EVENT_TYPES.items():
            self.assertIn("at", cls.model_fields)
            self.assertEqual(cls.model_fields["k"].default, k)
        self.assertIn("robber_stole", json.dumps(event_json_schema()))


if __name__ == "__main__":
    unittest.main()
