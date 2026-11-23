from dataclasses import replace

from django.test import SimpleTestCase

from engine import codec
from engine import game as engine
from engine.sim.bots import GreedyBot
from engine.sim.runner import replay
from engine.tests.fixtures import make_seats, make_settings, standard_board
from gamehost.core import SPECT, GameCore, group_name

REPLY = "reply.test"


def new_core(players: int = 3) -> tuple[GameCore, list]:
    settings, seats = make_settings(), make_seats(players)
    state, _ = engine.new_game(settings, seats, 7, board=standard_board())
    return GameCore(1, state), [settings, seats]


def play(core: GameCore, until_ms: int, think_ms: int = 1000) -> list:
    """Feed greedy-bot intents through the core like a host would."""
    bots = [GreedyBot(p.seat, 100 + p.seat) for p in core.state.players]
    out = []
    now = 0
    while now <= until_ms and not core.finished:
        out += core.advance(now)
        for bot in bots:
            for intent in bot.decide(core.state):
                out += core.intent(now, {"seat": bot.seat, "cid": "c", "payload": intent, "reply_channel": REPLY})
        now += think_ms
    return out


class GameCoreTests(SimpleTestCase):
    def test_reject_and_ack_replies(self):
        core, _ = new_core()
        out = core.intent(0, {"seat": 0, "cid": "a1", "payload": {"a": "nope"}, "reply_channel": REPLY})
        self.assertEqual(out[-1].kind, "channel")
        self.assertEqual(out[-1].target, REPLY)
        self.assertEqual(out[-1].message["msg"]["t"], "reject")
        self.assertEqual(out[-1].message["msg"]["cid"], "a1")
        self.assertEqual(core.cmd_seq, 0)
        out = core.intent(0, {"seat": "x", "cid": "a2", "payload": {}, "reply_channel": REPLY})
        self.assertEqual(out[-1].message["msg"]["code"], "command.unknown_seat")

        intent = GreedyBot(0, 1).decide(core.state)[0]
        out = core.intent(0, {"seat": 0, "cid": "a3", "payload": intent, "reply_channel": REPLY})
        self.assertIn({"t": "ack", "cid": "a3"}, [o.message["msg"] for o in out if o.kind == "channel"])
        self.assertEqual(core.cmd_seq, 1)
        self.assertEqual(len(core.pending), 1)

    def test_log_replays_to_same_state(self):
        core, (settings, seats) = new_core()
        play(core, 120_000)
        log = [rec for _n, rec in core.take_pending()]
        self.assertGreater(len(log), 5)
        rebuilt = replay(settings, seats, 7, log, until_ms=core.state.now_ms, board=standard_board())
        self.assertEqual(codec.state_hash(rebuilt), codec.state_hash(core.state))

    def test_each_audience_has_its_own_sequence(self):
        core, _ = new_core(2)
        out = play(core, 60_000)
        seen: dict[str, list[int]] = {}
        for o in out:
            if o.kind == "group":
                seen.setdefault(o.target, []).append(o.message["msg"]["seq"])
        self.assertEqual(set(seen), {group_name(1, 0), group_name(1, 1), group_name(1, None)})
        for seqs in seen.values():
            self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        self.assertEqual(core.seqs[SPECT], len(seen[group_name(1, None)]))

    def test_spectators_never_see_hand_contents(self):
        core, _ = new_core(2)
        out = play(core, 90_000)
        for o in out:
            if o.target == group_name(1, None):
                for ev in o.message["msg"]["events"]:
                    if ev["k"] == "hand":
                        self.assertNotIn("hand", ev)

    def test_sync_sends_board_then_state(self):
        core, _ = new_core()
        play(core, 10_000)
        out = core.sync({"seat": 1, "reply_channel": REPLY})
        board, state = (o.message["msg"] for o in out)
        self.assertEqual(board["t"], "board")
        self.assertEqual(state["t"], "state")
        self.assertEqual(state["seq"], core.seqs.get("1", 0))
        self.assertEqual(core.sync({"seat": 1}), [])

    def test_sync_board_follows_growing_sight(self):
        settings = make_settings({"visibility": {"map": "growing"}}, implemented_stage=3)
        state, _ = engine.new_game(settings, make_seats(3), 7, board=standard_board())
        core = GameCore(1, state)
        board = core.sync({"seat": 1, "reply_channel": REPLY})[0].message["msg"]
        self.assertTrue(board["partial"])
        self.assertLess(len(board["hexes"]), len(state.board.board.hexes))
        spect = core.sync({"seat": None, "reply_channel": REPLY})[0].message["msg"]
        self.assertEqual(len(spect["hexes"]), len(state.board.board.hexes))

    def test_resumed_messages_go_to_every_audience(self):
        core, _ = new_core(3)
        out = core.resumed_messages()
        self.assertEqual(len(out), 4)
        self.assertTrue(all(o.message["msg"]["resumed"] for o in out))


class HousekeepingTests(SimpleTestCase):
    """People who left are resigned for them; games that run far too long are ended."""

    def core(self, bots: int, **limits) -> GameCore:
        seats = [s if s.seat >= bots else replace(s, user_id=None) for s in make_seats(3)]
        state, _ = engine.new_game(make_settings(), seats, 7, board=standard_board())
        return GameCore(1, state, **limits)

    def test_off_by_default(self):
        core = self.core(2)
        self.assertEqual(core.housekeeping(10**9), [])

    def test_idle_person_is_resigned_and_bots_alone_end_the_game(self):
        core = self.core(2, idle_resign_ms=60_000)
        self.assertEqual(core.last_active, {2: 0})
        self.assertLessEqual(core.next_wakeup(), 60_000)
        core.advance(59_999)
        self.assertEqual(core.housekeeping(59_999), [])
        core.advance(60_000)
        core.housekeeping(60_000)
        self.assertTrue(core.state.player(2).resigned)
        self.assertTrue(core.finished)
        self.assertEqual(core.state.ext["victory"]["reason"], "resign")
        self.assertEqual(core.take_pending()[-1][1].payload, {"a": "resign"})

    def test_commands_keep_a_person_in(self):
        core = self.core(1, idle_resign_ms=60_000)
        intent = GreedyBot(1, 1).decide(core.state)[0]
        core.advance(50_000)
        core.intent(50_000, {"seat": 1, "payload": intent})
        self.assertEqual(core.last_active[1], 50_000)
        core.advance(70_000)
        core.housekeeping(70_000)
        self.assertFalse(core.state.player(1).resigned)
        self.assertTrue(core.state.player(2).resigned)     # never did anything
        self.assertFalse(core.finished)                     # a person is still playing

    def test_game_too_long_ends_with_the_leader(self):
        core = self.core(3, max_game_ms=120_000)
        self.assertEqual(core.last_active, {})
        play_bots(core, 119_000)
        self.assertFalse(core.finished)
        core.state.players[1].points = 3
        core.advance(120_000)
        core.housekeeping(120_000)
        self.assertTrue(core.finished)
        self.assertEqual(core.state.winner, 1)
        self.assertFalse(core.state.player(1).resigned)
        self.assertIsNone(core.next_wakeup())

    def test_housekept_log_replays(self):
        core = self.core(2, idle_resign_ms=30_000)
        play_bots(core, 40_000)
        log = [rec for _n, rec in core.take_pending()]
        self.assertIn({"a": "resign"}, [r.payload for r in log])
        rebuilt = replay(core.state.settings, [p.info for p in core.state.players], 7, log,
                         until_ms=core.state.now_ms, board=standard_board())
        self.assertEqual(codec.state_hash(rebuilt), codec.state_hash(core.state))


def play_bots(core: GameCore, until_ms: int, think_ms: int = 1000) -> None:
    """Computer players at every bot seat; the host's housekeeping runs after each tick."""
    bots = [GreedyBot(p.seat, 100 + p.seat) for p in core.state.players if p.info.user_id is None]
    now = 0
    while now <= until_ms and not core.finished:
        core.advance(now)
        for bot in bots:
            for intent in bot.decide(core.state):
                core.intent(now, {"seat": bot.seat, "payload": intent})
        core.housekeeping(now)
        now += think_ms
