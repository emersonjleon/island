import json
import unittest

from engine import codec, game
from engine.settings.enums import BuildKind, Resource
from engine.state import Building, Construction, GameState, Settler, SettlerStep
from engine.tests.fixtures import make_seats, make_settings, standard_board


def populated_state() -> GameState:
    settings = make_settings({"clock": {"roll_interval_ms": 8000}, "visibility": {"hands": "open"},
                              "board": {"number_tokens": {2: 1, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2, 9: 2, 10: 2,
                                                          11: 2, 12: 1}}})
    with game.temporary_registry(empty=True):
        state, _ = game.new_game(settings, make_seats(3), seed=42, board=standard_board())
    state.now_ms = 12345
    state.phase = "running"
    p0, p1 = state.players[0], state.players[1]
    p0.hand[Resource.LUMBER] = 3
    p1.hand[Resource.FISH] = 2
    state.bank[Resource.LUMBER] -= 3
    state.bank[Resource.FISH] -= 2
    p0.pieces_left[BuildKind.SETTLEMENT] -= 1
    p0.setup_remaining[BuildKind.SETTLEMENT] = 1
    p0.last_setup_settlement = 20
    p0.setup_settlements_built = 1
    p0.points = 1
    state.buildings[20] = Building(0, BuildKind.SETTLEMENT)
    state.buildings[5] = Building(1, BuildKind.CITY)
    state.roads[31] = 0
    state.roads[7] = 1
    sid = state.next_id("settler")
    tid = state.timers.schedule(13000, "settler_arrive", {"settler": sid})
    state.settlers[sid] = Settler(id=sid, seat=0, vertex=20, path=[22, 23],
                                  step=SettlerStep(edge=31, from_v=20, to_v=21, t0=11500, t1=13000), timer_id=tid)
    p0.settler_ids.append(sid)
    state.settlers[state.next_id("settler")] = Settler(id=2, seat=1, vertex=5)
    cid = state.next_id("construction")
    ctid = state.timers.schedule(15000, "construction_done", {"construction": cid})
    state.constructions[cid] = Construction(id=cid, seat=1, kind=BuildKind.ROAD, target=8, builder=None,
                                            paid={Resource.BRICK: 1, Resource.LUMBER: 1}, started_ms=12000,
                                            done_ms=15000, setup=False, timer_id=ctid)
    dead = state.timers.schedule(14000, "x")
    state.timers.cancel(dead)
    state.clock_started = True
    state.roll_timer_id = state.timers.schedule(16000, "dice_roll")
    state.next_roll_at = 16000
    state.last_roll = [3, 4]
    state.dice_history = [7, 8, 5]
    state.robber_hex = 4
    state.rng.randbelow(100)
    state.buildable_cache = {0: {"roads": [1, 2], "settlements": [], "cities": [20]}}
    state.ext = {"dev": {"deck": ["knight"]}, "offers": []}
    return state


class CodecTest(unittest.TestCase):
    def test_round_trip_through_json(self) -> None:
        s = populated_state()
        d = codec.dump(s)
        text = json.dumps(d)                       # JSON-safe
        s2 = codec.load(json.loads(text))
        self.assertEqual(codec.dump(s2), json.loads(text))
        self.assertEqual(codec.state_hash(s2), codec.state_hash(s))
        # typed content restored
        self.assertEqual(s2.buildings, s.buildings)
        self.assertEqual(s2.roads, s.roads)
        self.assertEqual(s2.settlers, s.settlers)
        self.assertEqual(s2.constructions, s.constructions)
        self.assertEqual(s2.players, s.players)
        self.assertEqual(s2.bank, s.bank)
        self.assertEqual(s2.settings, s.settings)
        self.assertEqual(s2.buildable_cache, s.buildable_cache)
        self.assertEqual(s2.board.board.hexes, s.board.board.hexes)
        self.assertEqual(s2.board.terrain, s.board.terrain)
        self.assertEqual(s2.board.token, s.board.token)
        self.assertEqual(s2.board.harbors, s.board.harbors)
        self.assertEqual(s2.board.fishing, s.board.fishing)
        self.assertEqual(s2.board.vertex_harbor, s.board.vertex_harbor)
        self.assertIsInstance(next(iter(s2.buildings)), int)
        self.assertIsInstance(next(iter(s2.players[0].hand)), Resource)

    def test_continuation_identical(self) -> None:
        s = populated_state()
        s2 = codec.load(json.loads(json.dumps(codec.dump(s))))
        self.assertEqual([s.rng.randbelow(1000) for _ in range(20)], [s2.rng.randbelow(1000) for _ in range(20)])
        self.assertEqual(s.next_id("settler"), s2.next_id("settler"))
        self.assertEqual(s.timers.schedule(1, "a"), s2.timers.schedule(1, "a"))
        self.assertEqual([t.to_list() for t in s.timers.pop_due(10**9)],
                         [t.to_list() for t in s2.timers.pop_due(10**9)])
        self.assertEqual(codec.state_hash(s), codec.state_hash(s2))

    def test_dump_is_detached(self) -> None:
        s = populated_state()
        h = codec.state_hash(s)
        d = codec.dump(s)
        d["ext"]["dev"]["deck"].append("monopoly")
        d["timers"]["timers"][0][4]["settler"] = 99
        d["buildable_cache"]["0"]["roads"].append(5)
        self.assertEqual(codec.state_hash(s), h)

    def test_hash_sensitive(self) -> None:
        s = populated_state()
        h = codec.state_hash(s)
        s.players[2].hand[Resource.ORE] += 1
        self.assertNotEqual(codec.state_hash(s), h)
        s.players[2].hand[Resource.ORE] -= 1
        self.assertEqual(codec.state_hash(s), h)
        s.rng.next_u32()
        self.assertNotEqual(codec.state_hash(s), h)

    def test_new_game_deterministic(self) -> None:
        with game.temporary_registry(empty=True):
            a, _ = game.new_game(make_settings(), make_seats(2), seed=5, board=standard_board())
            b, _ = game.new_game(make_settings(), make_seats(2), seed=5, board=standard_board())
            c, _ = game.new_game(make_settings(), make_seats(2), seed=6, board=standard_board())
        self.assertEqual(codec.state_hash(a), codec.state_hash(b))
        self.assertNotEqual(codec.state_hash(a), codec.state_hash(c))

    def test_rejects_unknown_version(self) -> None:
        d = codec.dump(populated_state())
        d["codec"] = 999
        with self.assertRaises(ValueError):
            codec.load(d)


if __name__ == "__main__":
    unittest.main()
