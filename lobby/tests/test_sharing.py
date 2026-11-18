from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from engine.settings import encode_share_code, load_preset
from lobby import services
from lobby.models import Game
from lobby.sharing import create_path, game_code


def user(name: str) -> User:
    return User.objects.create_user(name, f"{name}@example.com", "pw-unused-123")


class SettingsCodeTests(TestCase):
    def setUp(self):
        self.host = user("ana")
        self.client.force_login(self.host)

    def test_game_page_shows_code_and_link(self):
        game = services.create_game(self.host, "custom", {"players": {"max": 5}, "victory": {"target": 13}})
        code = game_code(game)
        response = self.client.get(reverse("lobby:detail", args=[game.code]))
        self.assertContains(response, code)
        self.assertContains(response, "http://testserver" + create_path(code).replace("&", "&amp;"))

    def test_create_from_code(self):
        source = services.create_game(self.host, "blitz", {"players": {"max": 3}, "board": {"red_may_touch": True}})
        response = self.client.post(reverse("lobby:list"), {
            "preset": "classic", "max_players": 6, "config": f"  {game_code(source)}\n"})
        game = Game.objects.exclude(pk=source.pk).get()
        self.assertRedirects(response, reverse("lobby:detail", args=[game.code]))
        self.assertEqual(game.preset, "blitz")
        self.assertEqual(game.overrides, source.overrides)
        self.assertEqual(load_preset(game.preset, game.overrides), load_preset(source.preset, source.overrides))

    def test_bad_code_shows_error(self):
        for code, text in (("classic.1.###", "not complete"), ("nope.1.", "game type"),
                           ("classic.99.", "newer version")):
            with self.subTest(code=code):
                response = self.client.post(reverse("lobby:list"),
                                            {"preset": "classic", "max_players": 4, "config": code})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)
        self.assertFalse(Game.objects.exists())

    def test_invalid_settings_in_code_refused(self):
        code = encode_share_code("classic", {"players": {"min": 4, "max": 3}})
        response = self.client.post(reverse("lobby:list"), {"preset": "classic", "max_players": 4, "config": code})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Game.objects.exists())

    def test_link_fills_form_and_previews(self):
        code = encode_share_code("custom", {"players": {"max": 5}, "victory": {"target": 13},
                                            "board": {"red_may_touch": True}})
        response = self.client.get(reverse("lobby:list"), {"config": code})
        self.assertContains(response, f'value="{code}"')
        preview = response.context["code_preview"]
        self.assertEqual(preview["players"], 5)
        self.assertIn("13", [value for _label, value in preview["stats"]])
        self.assertEqual(len(preview["changes"]), 1)

    def test_changes_listed_for_every_game_type(self):
        game = services.create_game(self.host, "classic", {"players": {"max": 4}, "board": {"red_may_touch": True}})
        response = self.client.get(reverse("lobby:detail", args=[game.code]))
        self.assertEqual(len(response.context["rule_changes"]), 1)
