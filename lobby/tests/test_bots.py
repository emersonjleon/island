from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from lobby import services
from lobby.models import BOT_NAMES, Game, GamePlayer, GameStatus
from lobby.services import LobbyError


def user(name: str, **extra) -> User:
    return User.objects.create_user(name, f"{name}@example.com", "pw-unused-123", **extra)


class BotServiceTests(TestCase):
    def setUp(self):
        self.host, self.bo = user("ana"), user("bo")
        self.game = services.create_game(self.host, "classic", {"players": {"max": 3}})

    def test_host_adds_ready_bots_with_free_colours_and_names(self):
        a = services.add_bot(self.game, self.host, "easy")
        b = services.add_bot(self.game, self.host, "hard")
        self.assertEqual((a.bot_level, a.bot_name, a.colour, a.ready, a.user), ("easy", BOT_NAMES[0], "blue", True, None))
        self.assertEqual((b.bot_name, b.colour), (BOT_NAMES[1], "white"))
        self.assertTrue(a.is_bot)
        self.assertEqual(a.display_name, f"{BOT_NAMES[0]} (bot)")
        with self.assertRaises(LobbyError) as ctx:
            services.add_bot(self.game, self.host, "medium")
        self.assertEqual(ctx.exception.code, "lobby.full")
        with self.assertRaises(LobbyError) as ctx:
            services.join_game(self.game, self.bo)
        self.assertEqual(ctx.exception.code, "lobby.full")

    def test_only_the_host_manages_bots(self):
        services.join_game(self.game, self.bo)
        with self.assertRaises(LobbyError) as ctx:
            services.add_bot(self.game, self.bo, "easy")
        self.assertEqual(ctx.exception.code, "lobby.not_host")
        bot = services.add_bot(self.game, self.host, "easy")
        with self.assertRaises(LobbyError) as ctx:
            services.remove_bot(self.game, self.bo, bot.pk)
        self.assertEqual(ctx.exception.code, "lobby.not_host")

    def test_bad_level_and_remove(self):
        with self.assertRaises(LobbyError) as ctx:
            services.add_bot(self.game, self.host, "godlike")
        self.assertEqual(ctx.exception.code, "lobby.bad_bot_level")
        bot = services.add_bot(self.game, self.host, "medium")
        services.remove_bot(self.game, self.host, bot.pk)
        self.assertFalse(GamePlayer.objects.filter(pk=bot.pk).exists())
        with self.assertRaises(LobbyError) as ctx:
            services.remove_bot(self.game, self.host, bot.pk)
        self.assertEqual(ctx.exception.code, "lobby.no_such_bot")
        host_seat = self.game.players.get(user=self.host)
        with self.assertRaises(LobbyError):
            services.remove_bot(self.game, self.host, host_seat.pk)  # people are not bots
        # a removed bot's name is free again
        self.assertEqual(services.add_bot(self.game, self.host, "easy").bot_name, BOT_NAMES[0])

    def test_one_person_and_bots_can_start(self):
        self.assertEqual(services.start_problems(self.game), ["lobby.too_few_players"])
        services.add_bot(self.game, self.host, "hard")
        self.assertEqual(services.start_problems(self.game), [])
        services.start_game(self.game, self.host)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, GameStatus.STARTING)
        self.assertEqual(sorted(self.game.players.values_list("seat", flat=True)), [0, 1])

    def test_host_leaving_never_hands_the_game_to_a_bot(self):
        services.add_bot(self.game, self.host, "easy")
        services.leave_game(self.game, self.host)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, GameStatus.ABORTED)

        game = services.create_game(self.host, "classic", {"players": {"max": 3}})
        services.add_bot(game, self.host, "easy")
        services.join_game(game, self.bo)
        services.leave_game(game, self.host)
        game.refresh_from_db()
        self.assertEqual((game.status, game.host), (GameStatus.LOBBY, self.bo))


class BotViewTests(TestCase):
    def setUp(self):
        self.host, self.bo = user("ana"), user("bo")
        self.game = services.create_game(self.host, "classic", {"players": {"max": 3}})
        self.detail = reverse("lobby:detail", args=[self.game.code])

    def test_host_sees_bot_controls_and_others_do_not(self):
        self.client.force_login(self.host)
        self.assertContains(self.client.get(self.detail), reverse("lobby:add_bot", args=[self.game.code]))
        self.client.force_login(self.bo)
        self.assertNotContains(self.client.get(self.detail), reverse("lobby:add_bot", args=[self.game.code]))

    def test_add_and_remove_through_views(self):
        self.client.force_login(self.host)
        response = self.client.post(reverse("lobby:add_bot", args=[self.game.code]), {"level": "hard"})
        self.assertRedirects(response, self.detail)
        bot = GamePlayer.objects.get(game=self.game, user=None)
        page = self.client.get(self.detail)
        self.assertContains(page, bot.bot_name)
        self.assertContains(page, "bot · Hard")
        self.assertContains(page, reverse("lobby:remove_bot", args=[self.game.code]))
        self.client.post(reverse("lobby:remove_bot", args=[self.game.code]), {"player": "junk"})
        self.assertTrue(GamePlayer.objects.filter(pk=bot.pk).exists())
        self.client.post(reverse("lobby:remove_bot", args=[self.game.code]), {"player": str(bot.pk)})
        self.assertFalse(GamePlayer.objects.filter(pk=bot.pk).exists())

    def test_bad_level_shows_message(self):
        self.client.force_login(self.host)
        response = self.client.post(reverse("lobby:add_bot", args=[self.game.code]), {"level": "x"}, follow=True)
        self.assertContains(response, "Unknown bot level.")
        self.assertFalse(Game.objects.get().players.filter(user=None).exists())

    def test_spanish(self):
        es = user("es", preferred_language="es")
        game = services.create_game(es, "classic", {"players": {"max": 3}})
        services.add_bot(game, es, "easy")
        self.client.force_login(es)
        page = self.client.get(reverse("lobby:detail", args=[game.code]))
        self.assertContains(page, "Añadir bot")
        self.assertContains(page, "bot · Fácil")
