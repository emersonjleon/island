"""Growing sight and hidden numbers (WP21): what each player is told."""
import json
import unittest
from typing import Any

from engine import codec, game, sight, views
from engine.settings.enums import BuildKind
from engine.settings import load_preset
from engine.sim.bots import make_bot
from engine.sim.runner import Simulation
from engine.rules.visibility import update_visibility
from engine.state import Building
from engine.tests.fixtures import make_seats, make_settings, standard_board

GROWING = {"visibility": {"map": "growing"}}
GROWING_HIDDEN = {"visibility": {"map": "growing", "hidden_numbers": True}}


def fog_settings(overrides: dict[str, Any] = GROWING):  # type: ignore[no-untyped-def]
    return make_settings(overrides, implemented_stage=3)


def new_state(overrides: dict[str, Any] = GROWING, seats: int = 3):  # type: ignore[no-untyped-def]
    state, events = game.new_game(fog_settings(overrides), make_seats(seats), 7, board=standard_board())
    return state, events


class SightTest(unittest.TestCase):
    def test_sight_ranges(self) -> None:
        gb = standard_board()
        v = gb.board.hex_vertices[9][0]
        self.assertEqual(sight.vertex_sight(gb, v, 0), set())
        self.assertEqual(sight.vertex_sight(gb, v, 1), set(gb.board.vertex_hexes[v]))
        two = sight.vertex_sight(gb, v, 2)
        for h in gb.board.vertex_hexes[v]:
            self.assertTrue(set(gb.board.hex_neighbors[h]) <= two)
        e = gb.board.hex_edges[9][0]
        self.assertEqual(sight.edge_sight(gb, e, 1), set(gb.board.edge_hexes[e]))

    def test_open_map_is_unchanged(self) -> None:
        state, _ = game.new_game(make_settings(), make_seats(3), 7, board=standard_board())
        self.assertEqual(views.board_for(state, 0), state.board.to_dict())
        self.assertNotIn("visibility", state.ext)
        self.assertEqual(views.project_state(state, 0)["visibility"], {"map": "open", "hidden_numbers": False})

    def test_start_sees_landing_area_only(self) -> None:
        state, events = new_state()
        revealed = [e for e in events if e.k == "revealed"]
        self.assertEqual(sorted(e.seat for e in revealed), [0, 1, 2])
        for p in state.players:
            seen = sight.seen_hexes(state, p.seat)
            settler = state.settlers[p.settler_ids[0]]
            self.assertEqual(seen, frozenset(state.board.board.vertex_hexes[settler.vertex]))
            board = views.board_for(state, p.seat)
            self.assertEqual({h["id"] for h in board["hexes"]}, seen)
            self.assertTrue(board["partial"])
        self.assertEqual(len(views.board_for(state, None)["hexes"]), len(state.board.board.hexes))

    def test_seen_never_shrinks_and_buildings_reveal(self) -> None:
        state, _ = new_state()
        before = sight.seen_hexes(state, 0)
        far = next(v for v in state.board.board.land_vertices
                   if not sight.vertex_seen(state.board, before, v))
        state.buildings[far] = Building(0, BuildKind.CITY)
        evs = update_visibility(state, 1)
        rev = [e for e in evs if e.k == "revealed" and e.seat == 0]
        self.assertEqual(len(rev), 1)
        after = sight.seen_hexes(state, 0)
        self.assertTrue(before < after)
        self.assertTrue(sight.vertex_sight(state.board, far, 2) <= after)
        self.assertEqual(rev[0].pieces["buildings"], [{"vertex": far, "seat": 0, "kind": "city"}])
        del state.buildings[far]
        self.assertEqual(update_visibility(state, 2), [])
        self.assertEqual(sight.seen_hexes(state, 0), after)

    def test_other_players_pieces_hidden_on_unseen_land(self) -> None:
        state, _ = new_state()
        seen0 = sight.seen_hexes(state, 0)
        hidden_v = next(v for v in state.board.board.land_vertices
                        if not sight.vertex_seen(state.board, seen0, v))
        state.buildings[hidden_v] = Building(1, BuildKind.SETTLEMENT)
        own_v = next(v for v in state.board.board.land_vertices
                     if not sight.vertex_seen(state.board, seen0, v) and v != hidden_v)
        state.buildings[own_v] = Building(0, BuildKind.SETTLEMENT)
        # before the hook runs, seat 0 has not seen either place
        p0 = views.project_state(state, 0)
        self.assertNotIn({"vertex": hidden_v, "seat": 1, "kind": "settlement"}, p0["buildings"])
        self.assertIn({"vertex": own_v, "seat": 0, "kind": "settlement"}, p0["buildings"])
        spect = views.project_state(state, None)
        self.assertIn({"vertex": hidden_v, "seat": 1, "kind": "settlement"}, spect["buildings"])

    def test_snapshot_keeps_seen(self) -> None:
        state, _ = new_state()
        restored = codec.load(json.loads(json.dumps(codec.dump(state))))
        for seat in range(3):
            self.assertEqual(sight.seen_hexes(restored, seat), sight.seen_hexes(state, seat))


class HiddenNumbersTest(unittest.TestCase):
    def test_open_map_hidden_numbers(self) -> None:
        overrides = {"visibility": {"hidden_numbers": True}}
        state, _ = new_state(overrides)
        board = views.board_for(state, 0)
        self.assertEqual(len(board["hexes"]), len(state.board.board.hexes))
        self.assertTrue(all(h["token"] is None for h in board["hexes"]))
        self.assertTrue(all(f["token"] is None for f in board["fishing"]))
        self.assertEqual(views.board_for(state, None), state.board.to_dict())
        v = state.board.board.hex_vertices[0][0]
        state.buildings[v] = Building(2, BuildKind.SETTLEMENT)
        evs = update_visibility(state, 1)
        self.assertEqual(len(evs), 1)
        shown = {h: t for h, t in evs[0].tokens.items()}
        self.assertTrue(shown)
        board = views.board_for(state, 0)
        tokens = {h["id"]: h["token"] for h in board["hexes"] if h["token"] is not None}
        self.assertEqual(tokens, shown)


# ------------------------------------------------------------------ no leaks
class NoLeakTest(unittest.TestCase):
    """Over seeded bot games, nothing a player receives is about land it has not seen,
    and no token shows before a building stands next to its hex."""

    def check_board(self, test, state, seat: int, board: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        seen = sight.seen_hexes(state, seat)
        numbers = sight.shown_numbers(state)
        for h in board["hexes"]:
            test.assertIn(h["id"], seen)
            if h["token"] is not None:
                test.assertIn(h["id"], numbers)
                test.assertEqual(h["token"], state.board.token[h["id"]])
        for v in board["vertices"]:
            test.assertTrue(v["hexes"])
            test.assertTrue(set(v["hexes"]) <= seen)
        for e in board["edges"]:
            test.assertTrue(set(e["hexes"]) <= seen)
        for f in board["fishing"]:
            test.assertIn(f["hex"], seen)
            if f["token"] is not None:
                test.assertIn(f["hex"], numbers)

    def check_pieces(self, state, seat: int, d: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        gb, seen = state.board, sight.seen_hexes(state, seat)
        if d.get("robber") is not None:
            self.assertIn(d["robber"], seen)
        for b in d.get("buildings", []):
            if b["seat"] != seat:
                self.assertTrue(sight.vertex_seen(gb, seen, b["vertex"]))
        for r in d.get("roads", []):
            if r["seat"] != seat:
                self.assertTrue(sight.edge_seen(gb, seen, r["edge"]))
        for s in d.get("settlers", []):
            if s["seat"] != seat:
                self.assertTrue(sight.vertex_seen(gb, seen, s["vertex"]))
                self.assertEqual(s["path"], [])

    def check_event(self, state, seat: int, d: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        gb, seen = state.board, sight.seen_hexes(state, seat)
        k = d["k"]
        if k == "revealed":
            self.assertEqual(d["seat"], seat)
            self.check_board(self, state, seat, d["board"])
            self.check_pieces(state, seat, d["pieces"])
        elif k == "numbers_revealed":
            for h in d["tokens"]:
                self.assertIn(int(h), seen)
        elif k in ("built", "construction_started") and d["seat"] != seat:
            if d["kind"] == "road":
                self.assertTrue(sight.edge_seen(gb, seen, d["target"]))
            else:
                self.assertTrue(sight.vertex_seen(gb, seen, d["target"]))
        elif k == "robber_moved":
            for key in ("from_hex", "to_hex"):
                self.assertTrue(d[key] is None or d[key] in seen)
        elif k == "dev_card_played" and d.get("hex") is not None and d["seat"] != seat:
            self.assertIn(d["hex"], seen)

    def run_game(self, seed: int, overrides: dict[str, Any], seats: int, rolls: int, preset: str = "classic") -> None:
        batches: list[list[Any]] = []
        settings = load_preset(preset, overrides, implemented_stage=3, players=seats)
        sim = Simulation(settings, make_seats(seats), seed,
                         [make_bot("greedy", i, seed * 1000 + i) for i in range(seats)],
                         on_events=batches.append)
        seen_before = {s: frozenset() for s in range(seats)}
        while not sim.state.finished and len(sim.state.dice_history) < rolls:
            batches.clear()
            sim.step()
            state = sim.state
            for seat in range(seats):
                seen = sight.seen_hexes(state, seat)
                self.assertTrue(seen_before[seat] <= seen)
                seen_before[seat] = seen
                for batch in batches:
                    for d in views.filter_events(batch, seat, state):
                        self.check_event(state, seat, d)
            for seat in range(seats):
                self.check_pieces(state, seat, views.project_state(state, seat))
        for seat in range(seats):
            self.check_board(self, sim.state, seat, views.board_for(sim.state, seat))
            self.assertLess(len(sight.seen_hexes(sim.state, seat)), len(sim.state.board.board.hexes))

    def test_seeded_games(self) -> None:
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self.run_game(seed, GROWING_HIDDEN, 3, 25)
        with self.subTest(huge=True):
            self.run_game(11, GROWING, 8, 15, preset="huge")


if __name__ == "__main__":
    unittest.main()
