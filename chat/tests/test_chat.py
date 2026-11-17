from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings

from accounts.models import User
from chat import codes, services
from chat.models import ChatMessage
from gameplay.routing import websocket_urlpatterns as game_ws
from lobby import services as lobby
from lobby.routing import websocket_urlpatterns as lobby_ws

TIMEOUT = 5


def make_user(name: str) -> User:
    return User.objects.create_user(name, f"{name}@example.com", "x")


class CleanTextTests(TestCase):
    def test_trims_and_joins_spaces(self):
        self.assertEqual(services.clean_text("  hola \n\t que  tal  "), "hola que tal")

    def test_refuses_empty_and_non_text(self):
        for bad in ["", "   ", "\n\n", None, 12, ["x"]]:
            with self.assertRaises(services.ChatError) as ctx:
                services.clean_text(bad)
            self.assertEqual(ctx.exception.code, codes.EMPTY)

    @override_settings(CHAT={"MAX_LENGTH": 10})
    def test_refuses_long_text(self):
        self.assertEqual(services.clean_text("x" * 10), "x" * 10)
        with self.assertRaises(services.ChatError) as ctx:
            services.clean_text("x" * 11)
        self.assertEqual((ctx.exception.code, ctx.exception.params), (codes.TOO_LONG, {"max": 10}))

    def test_keeps_emoji_and_accents(self):
        self.assertEqual(services.clean_text("¿Cambio 🌲🌲 por 🌾? ñandú"), "¿Cambio 🌲🌲 por 🌾? ñandú")


class PostAndHistoryTests(TestCase):
    def setUp(self):
        self.host = make_user("ana")
        self.game = lobby.create_game(self.host, "classic", {"players": {"max": 3}})

    def test_player_line_carries_colour(self):
        msg = services.post(self.game.pk, self.host, "hola")
        seat = self.game.players.get(user=self.host)
        self.assertEqual((msg["name"], msg["colour"], msg["player"], msg["text"]), ("ana", seat.colour, True, "hola"))
        self.assertIsInstance(msg["at"], int)

    def test_watcher_line_has_no_colour(self):
        msg = services.post(self.game.pk, make_user("eve"), "hi")
        self.assertEqual((msg["colour"], msg["player"], msg["seat"]), ("", False, None))

    @override_settings(CHAT={"HISTORY": 3})
    def test_history_is_latest_oldest_first(self):
        for i in range(5):
            services.post(self.game.pk, self.host, f"m{i}")
        self.assertEqual([m["text"] for m in services.history(self.game.pk)], ["m2", "m3", "m4"])

    def test_history_is_per_game(self):
        other = lobby.create_game(make_user("bo"), "classic", {"players": {"max": 2}})
        services.post(other.pk, other.host, "elsewhere")
        self.assertEqual(services.history(self.game.pk), [])

    def test_lines_go_with_their_game(self):
        services.post(self.game.pk, self.host, "hola")
        self.game.delete()
        self.assertFalse(ChatMessage.objects.exists())


class ChatSocketTests(TransactionTestCase):
    """The same conversation in the waiting room and in the game, over the pages' own sockets."""

    def setUp(self):
        self.layer = get_channel_layer()
        self.ana, self.bo = make_user("ana"), make_user("bo")
        self.game = lobby.create_game(self.ana, "classic", {"players": {"max": 2, "seat_order": "host"}})
        lobby.join_game(self.game, self.bo)

    def socket(self, routes, path, user) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(URLRouter(routes), path)
        comm.scope["user"] = user
        return comm

    async def open(self, routes, path, user) -> WebsocketCommunicator:
        comm = self.socket(routes, path, user)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        return comm

    async def recv(self, comm, kind: str) -> dict:
        while True:
            msg = await comm.receive_json_from(timeout=TIMEOUT)
            if msg["t"] == kind:
                return msg

    def test_waiting_room_chat(self):
        async def run():
            a = await self.open(lobby_ws, f"/ws/lobby/{self.game.code}/", self.ana)
            b = await self.open(lobby_ws, f"/ws/lobby/{self.game.code}/", self.bo)
            self.assertEqual(await self.recv(a, "chat"), {"t": "chat", "msgs": [], "history": True})
            await self.recv(b, "chat")
            await a.send_json_to({"t": "chat", "text": "  ¿listos? "})
            for comm in (a, b):
                got = await self.recv(comm, "chat")
                self.assertFalse(got["history"])
                self.assertEqual([(m["name"], m["text"]) for m in got["msgs"]], [("ana", "¿listos?")])
            await b.send_json_to({"t": "chat", "text": "   "})
            self.assertEqual((await self.recv(b, "notice"))["code"], codes.EMPTY)
            await a.disconnect()
            await b.disconnect()
            # Someone who opens the page later gets the conversation so far.
            cy = await database_sync_to_async(make_user)("cy")
            late = await self.open(lobby_ws, f"/ws/lobby/{self.game.code}/", cy)
            self.assertEqual([m["text"] for m in (await self.recv(late, "chat"))["msgs"]], ["¿listos?"])
            await late.disconnect()

        async_to_sync(run)()

    @override_settings(CHAT={"BURST": 2, "RATE_PER_SECOND": 0.001})
    def test_rate_limit(self):
        async def run():
            a = await self.open(lobby_ws, f"/ws/lobby/{self.game.code}/", self.ana)
            await self.recv(a, "chat")
            for i in range(3):
                await a.send_json_to({"t": "chat", "text": f"m{i}"})
            await self.recv(a, "chat")
            await self.recv(a, "chat")
            self.assertEqual((await self.recv(a, "notice"))["code"], codes.RATE_LIMITED)
            await a.disconnect()

        async_to_sync(run)()

    def test_conversation_carries_into_the_game(self):
        services.post(self.game.pk, self.bo, "suerte")
        lobby.set_ready(self.game, self.bo, True)
        lobby.start_game(self.game, self.ana)
        async_to_sync(self.layer.flush)()
        watcher = make_user("eve")

        async def run():
            path = f"/ws/play/{self.game.code}/"
            a = await self.open(game_ws, path, self.ana)
            w = await self.open(game_ws, path, watcher)
            history = await self.recv(a, "chat")
            self.assertEqual((history["history"], [m["text"] for m in history["msgs"]]), (True, ["suerte"]))
            await self.recv(w, "chat")
            # Players and people watching can talk; everyone on the game page hears it.
            await w.send_json_to({"t": "chat", "text": "gg"})
            await a.send_json_to({"t": "chat", "text": "doy 🌲 por 🌾"})
            for comm in (a, w):
                first = (await self.recv(comm, "chat"))["msgs"][0]
                second = (await self.recv(comm, "chat"))["msgs"][0]
                self.assertEqual((first["name"], first["player"]), ("eve", False))
                self.assertEqual((second["name"], second["player"], second["seat"]), ("ana", True, 0))
            await a.disconnect()
            await w.disconnect()

        async_to_sync(run)()
