import asyncio

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import InMemoryChannelLayer
from django.test import TransactionTestCase, override_settings

from accounts.models import User
from engine import codec
from engine import game as engine
from engine.sim.bots import GreedyBot
from gamehost import store
from gamehost.clock import ManualClock
from gamehost.leases import LocalLeases
from gamehost.models import GameCommand, GameSnapshot
from gamehost.runner import GameHost
from lobby import services
from lobby.models import Game, GamePlayer, GameStatus

TIMEOUT = 5


def started_lobby_game(players: int = 2) -> Game:
    users = [User.objects.create_user(f"p{i}", f"p{i}@example.com", "x") for i in range(players)]
    game = services.create_game(users[0], "classic", {"players": {"max": players}})
    for u in users[1:]:
        services.join_game(game, u)
        services.set_ready(game, u, True)
    return services.start_game(game, users[0])


@override_settings(GAMEHOST_FLUSH_MS=0, GAMEHOST_MAX_IDLE_MS=20, GAMEHOST_SNAPSHOT_EVERY_ROLLS=0)
class GameHostTests(TransactionTestCase):
    def setUp(self):
        self.layer = InMemoryChannelLayer()
        self.clocks: list[ManualClock] = []

    def host(self) -> GameHost:
        def clock(start):
            c = ManualClock(start)
            self.clocks.append(c)
            return c

        return GameHost(layer=self.layer, leases=LocalLeases(), clock_factory=clock)

    async def recv(self, channel: str) -> dict:
        return await asyncio.wait_for(self.layer.receive(channel), TIMEOUT)

    async def intent(self, host: GameHost, game_id: int, seat: int, payload: dict, cid: str = "c") -> dict:
        reply = await self.layer.new_channel()
        await host.dispatch({"type": "game.intent", "game_id": game_id, "seat": seat, "cid": cid,
                             "payload": payload, "reply_channel": reply})
        while True:
            msg = (await self.recv(reply))["msg"]
            if msg["t"] in ("ack", "reject"):
                return msg

    async def settle(self, runner) -> None:
        """Wait until the runner has caught up with the manual clock (fired every due timer)."""
        async def caught_up():
            while runner.core.state.now_ms < runner.clock.now() and not runner.core.finished:
                await asyncio.sleep(0.005)

        await asyncio.wait_for(caught_up(), TIMEOUT)

    async def play_some(self, host: GameHost, game_id: int, rounds: int = 6) -> int:
        """Greedy-bot intents through the real dispatch path; returns accepted count."""
        runner = host.runners[game_id]
        bots = [GreedyBot(p.seat, 50 + p.seat) for p in runner.core.state.players]
        accepted = 0
        for _ in range(rounds):
            self.clocks[-1].advance(1000)
            await self.settle(runner)
            for bot in bots:
                for payload in bot.decide(runner.core.state):
                    r = await self.intent(host, game_id, bot.seat, payload)
                    accepted += r["t"] == "ack"
        return accepted

    def test_start_flow(self):
        game = started_lobby_game()

        async def run():
            watcher = await self.layer.new_channel()
            await self.layer.group_add(game.group_name, watcher)
            host = self.host()
            await host.dispatch({"type": "game.start", "game_id": game.pk})
            self.assertEqual(await self.recv(watcher), {"type": "lobby.started", "url": f"/play/{game.code}/"})
            self.assertIn(game.pk, host.runners)
            await host.shutdown()

        async_to_sync(run)()
        game.refresh_from_db()
        self.assertEqual(game.status, GameStatus.RUNNING)
        self.assertIsNotNone(game.started_at)
        kinds = list(GameSnapshot.objects.filter(game=game).values_list("kind", flat=True))
        self.assertEqual(sorted(kinds), ["shutdown", "start"])

    def test_intents_sync_and_events(self):
        game = started_lobby_game()

        async def run():
            host = self.host()
            seat_group = await self.layer.new_channel()
            await self.layer.group_add("g.%d.seat.0" % game.pk, seat_group)
            await host.dispatch({"type": "game.start", "game_id": game.pk})
            reject = await self.intent(host, game.pk, 0, {"a": "build", "kind": "city", "vertex": 0}, cid="x1")
            self.assertEqual((reject["t"], reject["cid"]), ("reject", "x1"))
            self.assertGreater(await self.play_some(host, game.pk), 0)
            batch = (await self.recv(seat_group))["msg"]
            self.assertEqual((batch["t"], batch["seq"]), ("events", 1))

            reply = await self.layer.new_channel()
            await host.dispatch({"type": "game.sync", "game_id": game.pk, "seat": 0, "reply_channel": reply})
            self.assertEqual((await self.recv(reply))["msg"]["t"], "board")
            self.assertEqual((await self.recv(reply))["msg"]["t"], "state")
            await asyncio.sleep(0.1)  # let the runner flush
            accepted = host.runners[game.pk].core.cmd_seq
            await host.shutdown()
            return accepted

        accepted = async_to_sync(run)()
        self.assertEqual(GameCommand.objects.filter(game=game).count(), accepted)

    def test_intent_for_game_not_running(self):
        async def run():
            host = self.host()
            msg = await self.intent(host, 999, 0, {"a": "build"})
            self.assertEqual(msg["code"], "game.not_running")

        async_to_sync(run)()

    def test_slow_start_does_not_hold_up_the_receive_loop(self):
        async def run():
            host = self.host()
            release = asyncio.Event()

            async def slow_take(game_id):
                await release.wait()

            host.take = slow_take
            loop = asyncio.create_task(host.receive_loop())
            reply = await self.layer.new_channel()
            await self.layer.send(host.channel, {"type": "game.start", "game_id": 1})
            await self.layer.send(host.channel, {"type": "game.intent", "game_id": 2, "seat": 0, "cid": "x",
                                                 "payload": {"a": "build"}, "reply_channel": reply})
            msg = (await self.recv(reply))["msg"]
            self.assertEqual(msg["code"], "game.not_running")   # answered while the start still waits
            release.set()
            loop.cancel()

        async_to_sync(run)()

    def test_restore_after_crash_reproduces_state(self):
        game = started_lobby_game(3)

        async def crash():
            host = self.host()
            await host.dispatch({"type": "game.start", "game_id": game.pk})
            await self.play_some(host, game.pk, rounds=8)
            runner = host.runners[game.pk]
            await sync_to_async(store.flush_commands)(runner.core)
            hash_before, now_before = codec.state_hash(runner.core.state), runner.core.state.now_ms
            await host.stop_game(game.pk, snapshot=False)  # crash: no shutdown snapshot
            return hash_before, now_before

        hash_before, now_before = async_to_sync(crash)()
        self.assertFalse(GameSnapshot.objects.filter(game=game, kind="shutdown").exists())

        async def restore():
            watcher = await self.layer.new_channel()
            await self.layer.group_add("g.%d.spect" % game.pk, watcher)
            host = self.host()
            await host.scan()
            runner = host.runners[game.pk]
            msg = (await self.recv(watcher))["msg"]
            self.assertTrue(msg["resumed"])
            state = runner.core.state
            engine.advance(state, now_before)
            restored = codec.state_hash(state)
            await host.shutdown()
            return restored

        self.assertEqual(async_to_sync(restore)(), hash_before)

    def test_finished_game_writes_results(self):
        game = started_lobby_game(2)

        async def run():
            host = self.host()
            await host.dispatch({"type": "game.start", "game_id": game.pk})
            runner = host.runners[game.pk]
            state = runner.core.state
            state.phase, state.winner = "finished", 1
            state.players[1].points = 10
            state.players[0].points = 4
            await asyncio.wait_for(host.tasks[game.pk], TIMEOUT) if game.pk in host.tasks else None

        async_to_sync(run)()
        game.refresh_from_db()
        self.assertEqual(game.status, GameStatus.FINISHED)
        self.assertEqual(
            sorted(GamePlayer.objects.filter(game=game).values_list("seat", "final_points", "is_winner")),
            [(0, 4, False), (1, 10, True)],
        )
        self.assertTrue(GameSnapshot.objects.filter(game=game, kind="end").exists())

    def test_bad_starting_game_is_aborted(self):
        game = started_lobby_game(2)
        Game.objects.filter(pk=game.pk).update(settings={"board": {"land_hexes": -1}})

        async def run():
            host = self.host()
            self.assertIsNone(await host.take(game.pk))

        with self.assertLogs("gamehost.runner", "ERROR"):
            async_to_sync(run)()
        game.refresh_from_db()
        self.assertEqual(game.status, GameStatus.ABORTED)

    @override_settings(GAMEHOST_SNAPSHOTS_KEPT=2, GAMEHOST_SNAPSHOT_EVERY_ROLLS=1)
    def test_snapshot_every_roll_keeps_the_last_few(self):
        game = started_lobby_game(2)

        async def run():
            host = self.host()
            await host.dispatch({"type": "game.start", "game_id": game.pk})
            await self.play_some(host, game.pk, rounds=30)  # setup done, the dice clock runs
            runner = host.runners[game.pk]
            for _ in range(5):
                self.clocks[-1].advance(20_000)
                await self.settle(runner)
            st = host.runners[game.pk].core.state
            rolls = len(st.dice_history)
            await host.shutdown()
            return rolls

        self.assertGreaterEqual(async_to_sync(run)(), 5)
        kinds = sorted(GameSnapshot.objects.filter(game=game).values_list("kind", flat=True))
        self.assertEqual(kinds, ["roll", "shutdown"])


class HostRobustnessTests(TransactionTestCase):
    def test_concurrent_takes_start_one_runner(self):
        game = started_lobby_game(2)
        layer = InMemoryChannelLayer()

        async def run():
            host = GameHost(layer=layer, leases=LocalLeases(), clock_factory=ManualClock)
            await asyncio.gather(host.take(game.pk), host.take(game.pk), host.scan())
            self.assertEqual(len(host.tasks), 1)
            await host.shutdown()

        async_to_sync(run)()
        self.assertEqual(GameSnapshot.objects.filter(game=game, kind="start").count(), 1)

    def test_receive_loop_survives_layer_errors(self):
        class FlakyLayer(InMemoryChannelLayer):
            failures = 2

            async def receive(self, channel):
                if channel == "gamehost" and self.failures:
                    self.failures -= 1
                    raise TimeoutError("read timeout")
                return await super().receive(channel)

        layer = FlakyLayer()

        async def run():
            host = GameHost(layer=layer, leases=LocalLeases())
            loop = asyncio.create_task(host.receive_loop())
            reply = await layer.new_channel()
            await layer.send("gamehost", {"type": "game.intent", "game_id": 999, "cid": "c", "reply_channel": reply})
            msg = await asyncio.wait_for(layer.receive(reply), TIMEOUT)
            loop.cancel()
            return msg["msg"]["code"]

        self.assertEqual(async_to_sync(run)(), "game.not_running")
