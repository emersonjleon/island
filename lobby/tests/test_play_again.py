from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from lobby import services
from lobby.models import Game, GameStatus
from lobby.services import LobbyError


def user(name: str) -> User:
    return User.objects.create_user(name, f"{name}@example.com", "pw-unused-123")


OVERRIDES = {"players": {"max": 4}, "clock": {"roll_interval_ms": 9000}}


class PlayAgainTests(TestCase):
    def setUp(self):
        self.ana, self.bo, self.cy = user("ana"), user("bo"), user("cy")
        self.game = services.create_game(self.ana, "classic", OVERRIDES)
        services.join_game(self.game, self.bo)
        services.set_colour(self.game, self.bo, "green")
        services.add_bot(self.game, self.ana, "hard")
        services.add_bot(self.game, self.ana, "easy")
        Game.objects.filter(pk=self.game.pk).update(status=GameStatus.FINISHED)
        self.game.refresh_from_db()

    def seats(self, game: Game) -> list[tuple]:
        return sorted(
            (p.user.username if p.user else p.bot_name, p.bot_level, p.colour)
            for p in game.players.select_related("user")
        )

    def test_new_game_keeps_settings_size_and_bots(self):
        new = services.play_again(self.game, self.bo)
        self.assertNotEqual(new.pk, self.game.pk)
        self.assertEqual(new.status, GameStatus.LOBBY)
        self.assertEqual((new.preset, new.overrides), ("classic", OVERRIDES))
        self.assertEqual(new.host, self.bo)
        old_bots = [(n, lvl, c) for n, lvl, c in self.seats(self.game) if lvl]
        self.assertEqual(self.seats(new), sorted(old_bots + [("bo", "", "green")]))
        self.game.refresh_from_db()
        self.assertEqual(self.game.rematch, new)

    def test_other_players_join_the_same_new_game_with_their_colour(self):
        new = services.play_again(self.game, self.bo)
        self.game.refresh_from_db()
        again = services.play_again(self.game, self.ana)
        self.assertEqual(again.pk, new.pk)
        self.assertEqual(again.players.get(user=self.ana).colour, "red")
        self.assertEqual(Game.objects.count(), 2)
        self.assertEqual(services.play_again(self.game, self.ana).pk, new.pk)  # twice is harmless

    def test_a_new_game_is_made_when_the_first_one_is_gone(self):
        new = services.play_again(self.game, self.bo)
        services.cancel_game(new, self.bo)
        self.game.refresh_from_db()
        newer = services.play_again(self.game, self.ana)
        self.assertNotIn(newer.pk, (new.pk, self.game.pk))
        self.assertEqual(newer.host, self.ana)

    def test_refused_for_unfinished_games_and_outsiders(self):
        with self.assertRaises(LobbyError) as ctx:
            services.play_again(self.game, self.cy)
        self.assertEqual(ctx.exception.code, "lobby.not_joined")
        running = services.create_game(self.ana, "classic", {})
        with self.assertRaises(LobbyError) as ctx:
            services.play_again(running, self.ana)
        self.assertEqual(ctx.exception.code, "lobby.not_finished")


class PlayAgainViewTests(TestCase):
    def setUp(self):
        self.ana, self.bo, self.cy = user("ana"), user("bo"), user("cy")
        self.game = services.create_game(self.ana, "classic", {"players": {"max": 3}})
        services.join_game(self.game, self.bo)
        Game.objects.filter(pk=self.game.pk).update(status=GameStatus.FINISHED)

    def detail(self, who: User):
        self.client.force_login(who)
        return self.client.get(reverse("lobby:detail", args=[self.game.code]))

    def test_button_shows_on_a_finished_game_for_its_players(self):
        self.assertContains(self.detail(self.ana), reverse("lobby:play_again", args=[self.game.code]))
        self.assertNotContains(self.detail(self.cy), reverse("lobby:play_again", args=[self.game.code]))

    def test_press_goes_to_the_new_game_and_invites_the_others(self):
        self.client.force_login(self.ana)
        response = self.client.post(reverse("lobby:play_again", args=[self.game.code]))
        self.game.refresh_from_db()
        new = self.game.rematch
        self.assertRedirects(response, reverse("lobby:detail", args=[new.code]))
        page = self.detail(self.bo)
        self.assertContains(page, "Join the new game")
        self.assertContains(page, "ana")
        self.client.post(reverse("lobby:play_again", args=[self.game.code]))
        self.assertTrue(new.players.filter(user=self.bo).exists())
        self.assertContains(self.detail(self.bo), reverse("lobby:detail", args=[new.code]))

    def test_no_button_while_the_game_is_open(self):
        Game.objects.filter(pk=self.game.pk).update(status=GameStatus.LOBBY)
        self.assertNotContains(self.detail(self.ana), reverse("lobby:play_again", args=[self.game.code]))
