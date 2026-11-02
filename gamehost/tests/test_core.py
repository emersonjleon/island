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

    def test_resumed_messages_go_to_every_audience(self):
        core, _ = new_core(3)
        out = core.resumed_messages()
        self.assertEqual(len(out), 4)
        self.assertTrue(all(o.message["msg"]["resumed"] for o in out))
