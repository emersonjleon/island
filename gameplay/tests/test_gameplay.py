import asyncio
from unittest import mock
from asgiref.sync import async_to_sync
from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import User
from engine.sim.bots import GreedyBot
from gameplay import codes
from gameplay.ratelimit import TokenBucket
from gameplay.routing import websocket_urlpatterns
from gamehost.clock import ManualClock
from gamehost.leases import LocalLeases
from gamehost.runner import GameHost
from lobby import services
from lobby.models import Game, GameStatus

TIMEOUT = 5


def started_game(players: int = 2) -> tuple[Game, list[User]]:
    users = [User.objects.create_user(f"p{i}", f"p{i}@example.com", "x") for i in range(players)]
    game = services.create_game(users[0], "classic", {"players": {"max": players, "seat_order": "host"}})
    for u in users[1:]:
        services.join_game(game, u)
        services.set_ready(game, u, True)
    return services.start_game(game, users[0]), users


class PlayViewTests(TestCase):
    def test_requires_login(self):
        game, _ = started_game()
        url = reverse("gameplay:play", args=[game.code])
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_lobby_game_redirects_to_lobby(self):
        user = User.objects.create_user("solo", "s@example.com", "x")
        game = services.create_game(user, "classic", {"players": {"max": 2}})
        self.client.force_login(user)
        response = self.client.get(reverse("gameplay:play", args=[game.code]))
        self.assertRedirects(response, reverse("lobby:detail", args=[game.code]))

    def test_page_carries_config(self):
        game, users = started_game()
        users[1].keybindings = {"build_road": ["KeyR"]}
        users[1].save()
        self.client.force_login(users[1])
        response = self.client.get(reverse("gameplay:play", args=[game.code.lower()]))
        config = response.context["config"]
        self.assertEqual(config["seat"], 1)
        self.assertEqual(config["wsPath"], f"/ws/play/{game.code}/")
        self.assertEqual(config["keybindings"], {"build_road": ["KeyR"]})
        self.assertContains(response, 'id="game-config"')

    def test_spectator_page(self):
        game, _ = started_game()
        watcher = User.objects.create_user("watcher", "w@example.com", "x")
        self.client.force_login(watcher)
        response = self.client.get(reverse("gameplay:play", args=[game.code]))
        self.assertIsNone(response.context["config"]["seat"])
        self.assertContains(response, "spectator")


class TokenBucketTests(SimpleTestCase):
    def test_refills_over_time(self):
        now = [0.0]
        bucket = TokenBucket(rate=2, burst=2, clock=lambda: now[0])
        self.assertEqual([bucket.take() for _ in range(3)], [True, True, False])
        now[0] = 0.5
        self.assertTrue(bucket.take())
        self.assertFalse(bucket.take())


@override_settings(GAMEHOST_FLUSH_MS=0, GAMEHOST_MAX_IDLE_MS=20, GAMEHOST_SNAPSHOT_EVERY_ROLLS=0)
class GameConsumerTests(TransactionTestCase):
    """The consumer against a real in-process game host on the in-memory channel layer."""

    def setUp(self):
        self.layer = get_channel_layer()
        self.app = URLRouter(websocket_urlpatterns)
        self.game, self.users = started_game(2)
        async_to_sync(self.layer.flush)()  # drop the lobby's game.start; tests start the host themselves

    def ws(self, user, code=None) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(self.app, f"/ws/play/{code or self.game.code}/")
        comm.scope["user"] = user
        return comm

    async def start_host(self) -> GameHost:
        self.clock = None

        def clock(start):
            self.clock = ManualClock(start)
            return self.clock

        host = GameHost(layer=self.layer, leases=LocalLeases(), clock_factory=clock)
        self.receiver = asyncio.create_task(host.receive_loop())
        await host.take(self.game.pk)
        return host

    async def stop_host(self, host: GameHost) -> None:
        self.receiver.cancel()
        await host.shutdown()

    async def recv(self, comm, kind: str | None = None) -> dict:
        while True:
            msg = await comm.receive_json_from(timeout=TIMEOUT)
            if kind is None or msg["t"] == kind:
                return msg

    async def connect(self, user) -> WebsocketCommunicator:
        comm = self.ws(user)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        return comm

    def test_refuses_anonymous_unknown_and_lobby_games(self):
        lobby_game = services.create_game(self.users[0], "classic", {"players": {"max": 2}})

        async def run():
            for user, code in [(AnonymousUser(), None), (self.users[0], "ZZZZZ"), (self.users[0], lobby_game.code)]:
                connected, close_code = await self.ws(user, code).connect()
                self.assertFalse(connected)

        async_to_sync(run)()

    def test_welcome_board_state_and_play(self):
        async def run():
            host = await self.start_host()
            player = await self.connect(self.users[0])
            welcome = await self.recv(player)
            self.assertEqual((welcome["t"], welcome["seat"], welcome["game"]), ("welcome", 0, self.game.code))
            self.assertIn("board", welcome["settings"])
            self.assertEqual((await self.recv(player))["t"], "board")
            state = await self.recv(player)
            self.assertEqual(state["t"], "state")
            self.assertIn("hand", state["state"]["players"][0])

            await player.send_json_to({"t": "hello", "proto": 1, "lang": "es"})
            await player.send_json_to({"t": "ping", "c": 12.5})
            pong = await self.recv(player, "pong")
            self.assertEqual(pong["c"], 12.5)
            self.assertIsInstance(pong["now"], int)

            runner = host.runners[self.game.pk]
            payload = GreedyBot(0, 1).decide(runner.core.state)[0]
            await player.send_json_to({"t": "intent", "cid": "a1", **payload})
            self.assertEqual(await self.recv(player, "ack"), {"t": "ack", "cid": "a1"})
            batch = await self.recv(player, "events")
            self.assertEqual(batch["seq"], 1)

            await player.send_json_to({"t": "intent", "cid": "a2", "a": "build", "kind": "city", "vertex": 0})
            reject = await self.recv(player, "reject")
            self.assertEqual(reject["cid"], "a2")

            await player.send_json_to({"t": "intent", "cid": "a3", "a": "fly"})
            self.assertEqual((await self.recv(player, "reject"))["code"], "command.invalid")
            await player.disconnect()
            await self.stop_host(host)

        async_to_sync(run)()

    def test_spectator_sees_redacted_state_and_cannot_act(self):
        watcher = User.objects.create_user("watcher", "w@example.com", "x")

        async def run():
            host = await self.start_host()
            spect = await self.connect(watcher)
            self.assertIsNone((await self.recv(spect, "welcome"))["seat"])
            state = await self.recv(spect, "state")
            self.assertTrue(all("hand" not in p for p in state["state"]["players"]))
            await spect.send_json_to({"t": "intent", "cid": "s1", "a": "build", "kind": "road", "edge": 1})
            self.assertEqual((await self.recv(spect, "reject"))["code"], codes.INTENT_SPECTATOR)
            await spect.disconnect()
            await self.stop_host(host)

        async_to_sync(run)()

    def test_edge_checks(self):
        from gameplay import consumers

        async def run():
            host = await self.start_host()
            player = await self.connect(self.users[1])
            await self.recv(player, "state")
            await player.send_to(text_data="x" * (consumers.MAX_MESSAGE_BYTES + 1))
            self.assertEqual((await self.recv(player, "notice"))["code"], codes.MESSAGE_TOO_LARGE)
            await player.send_to(text_data="not json")
            self.assertEqual((await self.recv(player, "notice"))["code"], codes.MESSAGE_INVALID)
            await player.send_json_to({"t": "intent", "a": "build"})
            self.assertEqual((await self.recv(player, "reject"))["code"], codes.INTENT_BAD_CID)
            for i in range(consumers.INTENTS_PER_SECOND + 5):
                await player.send_json_to({"t": "intent", "cid": f"r{i}", "a": "fly"})
            seen = set()
            for _ in range(consumers.INTENTS_PER_SECOND + 5):
                seen.add((await self.recv(player, "reject"))["code"])
            self.assertIn(codes.INTENT_RATE_LIMITED, seen)
            await player.send_json_to({"t": "hello", "proto": 99})
            self.assertEqual((await self.recv(player, "notice"))["code"], codes.PROTO_UNSUPPORTED)
            self.assertEqual((await player.receive_output(TIMEOUT))["type"], "websocket.close")
            await self.stop_host(host)

        async_to_sync(run)()

    def test_intent_without_host_is_rejected_as_not_running(self):
        Game.objects.filter(pk=self.game.pk).update(status=GameStatus.RUNNING)

        async def run():
            host = GameHost(layer=self.layer, leases=LocalLeases())
            receiver = asyncio.create_task(host.receive_loop())
            player = await self.connect(self.users[0])
            await self.recv(player, "welcome")
            await player.send_json_to({"t": "intent", "cid": "z", "a": "build", "kind": "road", "edge": 1})
            self.assertEqual((await self.recv(player, "reject"))["code"], codes.GAME_NOT_RUNNING)
            await player.disconnect()
            receiver.cancel()

        async_to_sync(run)()

    def test_full_host_channel(self):
        """A full gamehost channel refuses orders with game.busy and closes a connection whose sync was lost."""
        from gameplay import consumers

        layer_send = self.layer.send
        full = {"on": False}

        async def send(channel, message):
            if full["on"] and channel == "gamehost":
                raise ChannelFull()
            return await layer_send(channel, message)

        async def run():
            with mock.patch.object(self.layer, "send", send):
                player = await self.connect(self.users[0])
                await self.recv(player, "welcome")
                full["on"] = True
                await player.send_json_to({"t": "intent", "cid": "b1", "a": "build", "kind": "road", "edge": 1})
                reject = await self.recv(player, "reject")
                self.assertEqual((reject["cid"], reject["code"]), ("b1", codes.GAME_BUSY))
                await player.disconnect()

                late = self.ws(self.users[1])
                connected, _ = await late.connect()
                self.assertTrue(connected)
                await self.recv(late, "welcome")
                closed = await late.receive_output(TIMEOUT)
                self.assertEqual((closed["type"], closed.get("code")), ("websocket.close", consumers.TRY_AGAIN_LATER))

        async_to_sync(run)()
