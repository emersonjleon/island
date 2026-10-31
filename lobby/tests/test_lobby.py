from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts.models import User
from engine.settings import GameSettings
from lobby import services
from lobby.consumers import LobbyConsumer  # noqa: F401  (routing import check)
from lobby.models import CODE_ALPHABET, CODE_LENGTH, Game, GamePlayer, GameStatus
from lobby.routing import websocket_urlpatterns
from lobby.services import LobbyError


def user(name: str) -> User:
    return User.objects.create_user(name, f"{name}@example.com", "pw-unused-123")


def receive_nowait(channel: str):
    layer = get_channel_layer()
    return async_to_sync(layer.receive)(channel)


class ServiceTests(TestCase):
    def setUp(self):
        self.host, self.bo, self.cy = user("ana"), user("bo"), user("cy")

    def make(self, overrides=None, preset="classic") -> Game:
        return services.create_game(self.host, preset, overrides or {"players": {"max": 3}})

    def test_create_seats_host_with_first_colour(self):
        game = self.make()
        self.assertEqual(len(game.code), CODE_LENGTH)
        self.assertTrue(set(game.code) <= set(CODE_ALPHABET))
        self.assertEqual(game.status, GameStatus.LOBBY)
        self.assertEqual(list(game.players.values_list("user__username", "colour")), [("ana", "red")])

    def test_create_rejects_bad_settings(self):
        with self.assertRaises(LobbyError) as ctx:
            self.make({"players": {"min": 4, "max": 3}})
        self.assertEqual(ctx.exception.code, "lobby.invalid_settings")
        with self.assertRaises(LobbyError) as ctx:
            self.make(preset="nope")
        self.assertEqual(ctx.exception.code, "lobby.unknown_preset")
        self.assertFalse(Game.objects.exists())

    def test_join_assigns_free_colours_and_respects_capacity(self):
        game = self.make({"players": {"max": 2}})
        seat = services.join_game(game, self.bo)
        self.assertEqual(seat.colour, "blue")
        self.assertEqual(services.join_game(game, self.bo).pk, seat.pk)  # joining twice is a no-op
        with self.assertRaises(LobbyError) as ctx:
            services.join_game(game, self.cy)
        self.assertEqual(ctx.exception.code, "lobby.full")

    def test_colour_change(self):
        game = self.make()
        services.join_game(game, self.bo)
        services.set_colour(game, self.bo, "green")
        self.assertEqual(game.players.get(user=self.bo).colour, "green")
        with self.assertRaises(LobbyError) as ctx:
            services.set_colour(game, self.bo, "red")
        self.assertEqual(ctx.exception.code, "lobby.colour_taken")
        with self.assertRaises(LobbyError):
            services.set_colour(game, self.bo, "purple")
        with self.assertRaises(LobbyError) as ctx:
            services.set_colour(game, self.cy, "white")
        self.assertEqual(ctx.exception.code, "lobby.not_joined")

    def test_host_leaving_hands_over_or_cancels(self):
        game = self.make()
        services.join_game(game, self.bo)
        services.leave_game(game, self.host)
        game.refresh_from_db()
        self.assertEqual(game.host, self.bo)
        self.assertEqual(game.status, GameStatus.LOBBY)
        services.leave_game(game, self.bo)
        game.refresh_from_db()
        self.assertEqual(game.status, GameStatus.ABORTED)
        self.assertFalse(game.players.exists())

    def test_start_requirements(self):
        game = self.make()
        self.assertEqual(services.start_problems(game), ["lobby.too_few_players"])
        services.join_game(game, self.bo)
        self.assertEqual(services.start_problems(game), ["lobby.not_all_ready"])
        with self.assertRaises(LobbyError) as ctx:
            services.start_game(game, self.host)
        self.assertEqual(ctx.exception.code, "lobby.not_all_ready")
        services.set_ready(game, self.bo, True)
        self.assertEqual(services.start_problems(game), [])
        with self.assertRaises(LobbyError) as ctx:
            services.start_game(game, self.bo)
        self.assertEqual(ctx.exception.code, "lobby.not_host")

    def test_start_fixes_seed_seats_settings_and_notifies_gamehost(self):
        game = self.make({"players": {"max": 3}, "board": {"land_hexes": 37}, "victory": {"target": 8}})
        services.join_game(game, self.bo)
        services.join_game(game, self.cy)
        services.set_ready(game, self.bo, True)
        services.set_ready(game, self.cy, True)
        with self.captureOnCommitCallbacks(execute=True):
            services.start_game(game, self.host)
        game.refresh_from_db()
        self.assertEqual(game.status, GameStatus.STARTING)
        self.assertIsNotNone(game.seed)
        settings = GameSettings.model_validate(game.settings)
        self.assertEqual((settings.board.land_hexes, settings.victory.target), (37, 8))
        self.assertEqual(sorted(game.players.values_list("seat", flat=True)), [0, 1, 2])
        self.assertEqual(receive_nowait("gamehost"), {"type": "game.start", "game_id": game.pk})
        with self.assertRaises(LobbyError) as ctx:
            services.join_game(game, user("dee"))
        self.assertEqual(ctx.exception.code, "lobby.not_open")

    def test_host_seat_order_keeps_join_order(self):
        game = self.make({"players": {"max": 3, "seat_order": "host"}})
        services.join_game(game, self.bo)
        services.set_ready(game, self.bo, True)
        services.start_game(game, self.host)
        self.assertEqual(
            list(game.players.order_by("seat").values_list("user__username", flat=True)), ["ana", "bo"]
        )

    def test_cancel_only_by_host(self):
        game = self.make()
        services.join_game(game, self.bo)
        with self.assertRaises(LobbyError):
            services.cancel_game(game, self.bo)
        services.cancel_game(game, self.host)
        game.refresh_from_db()
        self.assertEqual(game.status, GameStatus.ABORTED)


class ViewTests(TestCase):
    def setUp(self):
        self.host, self.bo = user("ana"), user("bo")

    def test_lobby_requires_login(self):
        response = self.client.get(reverse("lobby:list"))
        self.assertRedirects(response, reverse("accounts:login") + "?next=" + reverse("lobby:list"))

    def test_create_from_form(self):
        self.client.force_login(self.host)
        response = self.client.post(
            reverse("lobby:list"),
            {"preset": "classic", "max_players": "3", "land_hexes": "37", "roll_interval": "15", "target": ""},
        )
        game = Game.objects.get()
        self.assertRedirects(response, reverse("lobby:detail", args=[game.code]))
        self.assertEqual(
            game.overrides,
            {"players": {"max": 3}, "board": {"land_hexes": 37}, "clock": {"roll_interval_ms": 15000}},
        )

    def test_create_form_rejects_out_of_range(self):
        self.client.force_login(self.host)
        response = self.client.post(reverse("lobby:list"), {"preset": "classic", "max_players": "3", "land_hexes": "3"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Game.objects.exists())

    def test_list_shows_open_games(self):
        game = services.create_game(self.host, "classic", {"players": {"max": 4}})
        self.client.force_login(self.bo)
        self.assertContains(self.client.get(reverse("lobby:list")), game.code)

    def test_join_ready_start_through_views(self):
        game = services.create_game(self.host, "classic", {"players": {"max": 2}})
        self.client.force_login(self.bo)
        detail = reverse("lobby:detail", args=[game.code])
        self.assertContains(self.client.get(detail), reverse("lobby:join", args=[game.code]))
        self.assertRedirects(self.client.post(reverse("lobby:join", args=[game.code])), detail)
        self.client.post(reverse("lobby:ready", args=[game.code]), {"ready": "1"})
        self.assertTrue(GamePlayer.objects.get(user=self.bo).ready)
        response = self.client.post(reverse("lobby:start", args=[game.code]), follow=True)
        self.assertContains(response, "Only the host can do that.")
        self.client.force_login(self.host)
        self.client.post(reverse("lobby:start", args=[game.code]))
        game.refresh_from_db()
        self.assertEqual(game.status, GameStatus.STARTING)
        self.assertContains(self.client.get(detail), "The island is being prepared.")

    def test_lowercase_code_works(self):
        game = services.create_game(self.host, "classic", {"players": {"max": 2}})
        self.client.force_login(self.host)
        self.assertEqual(self.client.get(reverse("lobby:detail", args=[game.code.lower()])).status_code, 200)

    def test_seats_fragment(self):
        game = services.create_game(self.host, "classic", {"players": {"max": 2}})
        self.client.force_login(self.host)
        response = self.client.get(reverse("lobby:seats", args=[game.code]))
        self.assertContains(response, "<table class=\"seats\">")
        self.assertNotContains(response, "<html")

    def test_spanish(self):
        self.client.force_login(User.objects.create_user("es", "es@example.com", "x", preferred_language="es"))
        self.assertContains(self.client.get(reverse("lobby:list")), "Crear partida")


class ConsumerTests(TransactionTestCase):
    def setUp(self):
        self.host = user("ana")
        self.game = services.create_game(self.host, "classic", {"players": {"max": 3}})
        self.app = URLRouter(websocket_urlpatterns)

    def communicator(self, user_obj, code=None):
        comm = WebsocketCommunicator(self.app, f"/ws/lobby/{code or self.game.code}/")
        comm.scope["user"] = user_obj
        return comm

    def test_rejects_anonymous_and_unknown_game(self):
        from django.contrib.auth.models import AnonymousUser

        async def run():
            connected, _ = await self.communicator(AnonymousUser()).connect()
            self.assertFalse(connected)
            connected, _ = await self.communicator(self.host, code="ZZZZZ").connect()
            self.assertFalse(connected)

        async_to_sync(run)()

    def test_changed_and_started_messages(self):
        bo = user("bo")

        async def run():
            comm = self.communicator(self.host)
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.send_json_to({"t": "ping"})
            self.assertEqual(await comm.receive_json_from(), {"t": "pong"})
            from channels.db import database_sync_to_async

            await database_sync_to_async(services.join_game)(self.game, bo)
            self.assertEqual(await comm.receive_json_from(), {"t": "changed"})
            await database_sync_to_async(services.notify_started)(self.game)
            self.assertEqual(await comm.receive_json_from(), {"t": "started", "url": f"/play/{self.game.code}/"})
            await comm.disconnect()

        async_to_sync(run)()
