from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from engine.settings import load_preset
from lobby import services
from lobby.models import Game, GamePlayer, SavedSettings
from lobby.prefill import settings_form_data
from lobby.forms import CreateGameForm
from lobby.services import LobbyError


def user(name: str) -> User:
    return User.objects.create_user(name, f"{name}@example.com", "pw-unused-123")


class PrefillTests(TestCase):
    def test_form_data_round_trip(self):
        cases = [("classic", {"players": {"max": 4}}),
                 ("blitz", {"players": {"max": 6}, "victory": {"target": 9}, "robber": {"enabled": False}}),
                 ("huge", {"players": {"max": 8}, "dev_cards": {"road_building_roads": 3},
                           "economy": {"costs": {"road": {"lumber": 2, "brick": 1}}}}),
                 ("custom", {"players": {"max": 3}, "build": {"time_ms": {"megacity": 20000}}})]
        for preset, overrides in cases:
            with self.subTest(preset=preset):
                form = CreateGameForm(settings_form_data(preset, overrides))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(load_preset(form.chosen_preset(), form.overrides()),
                                 load_preset(preset, overrides).model_copy(update={"preset": form.chosen_preset()}))


class SavedSettingsTests(TestCase):
    def setUp(self):
        self.host, self.bo = user("ana"), user("bo")
        self.game = services.create_game(self.host, "blitz", {"players": {"max": 3}, "victory": {"target": 9}})

    def test_save_from_game_page_and_use(self):
        self.client.force_login(self.bo)
        self.client.post(reverse("lobby:save_settings", args=[self.game.code]), {"name": "  Rápida   9  "})
        saved = SavedSettings.objects.get(owner=self.bo)
        self.assertEqual((saved.name, saved.preset, saved.overrides), ("Rápida 9", "blitz", self.game.overrides))
        page = self.client.get(reverse("lobby:list"))
        self.assertContains(page, "Rápida 9")
        use = page.context["saved_settings"][0]["use_url"]
        filled = self.client.get(use)
        self.assertEqual(filled.context["active_saved"], saved)
        self.assertTrue(filled.context["saved_settings"][0]["active"])
        self.assertEqual(filled.context["chosen_preset"], "custom")
        form = filled.context["form"]
        self.assertEqual((form.data["base"], form.data["max_players"], form.data["target"]), ("blitz", "3", "9"))
        # one click on "Create game" with what the form now holds
        created = self.client.post(reverse("lobby:list"), dict(form.data))
        game = Game.objects.exclude(pk=self.game.pk).get()
        self.assertRedirects(created, reverse("lobby:detail", args=[game.code]))
        self.assertEqual(load_preset(game.preset, game.overrides).victory.target, 9)

    def test_save_from_create_form(self):
        self.client.force_login(self.bo)
        data = settings_form_data("classic", {"players": {"max": 5}, "victory": {"target": 12}})
        res = self.client.post(reverse("lobby:list"), {**data, "save_as": "1", "save_name": "Larga"})
        saved = SavedSettings.objects.get(owner=self.bo)
        self.assertRedirects(res, reverse("lobby:list") + f"?saved={saved.pk}#create-game", fetch_redirect_response=False)
        self.assertFalse(Game.objects.exclude(pk=self.game.pk).exists())
        self.assertEqual(load_preset(saved.preset, saved.overrides).victory.target, 12)
        res = self.client.post(reverse("lobby:list"), {**data, "save_as": "1", "save_name": " "})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context["form"].non_field_errors())

    def test_at_most_ten(self):
        for i in range(services.MAX_SAVED_PER_USER):
            services.save_settings(self.bo, f"s{i}", "classic", {})
        with self.assertRaises(LobbyError):
            services.save_settings(self.bo, "one more", "classic", {})
        services.save_settings(self.bo, "s3", "blitz", {})  # replacing by name still works
        self.assertEqual(services.MAX_SAVED_PER_USER, 10)

    def test_other_users_saved_settings_are_not_used(self):
        mine = services.save_settings(self.host, "ana's", "blitz", {})
        self.client.force_login(self.bo)
        page = self.client.get(reverse("lobby:list") + f"?saved={mine.pk}")
        self.assertIsNone(page.context["active_saved"])
        self.assertEqual(page.context["chosen_preset"], "classic")

    def test_new_types_live_inside_custom_first(self):
        self.client.force_login(self.bo)
        page = self.client.get(reverse("lobby:list"))
        cards = [c["name"] for c in page.context["preset_cards"]]
        for name in ("settlers", "explorer", "ages", "ages_big", "friendly"):
            self.assertNotIn(name, cards)
        choices = [p["name"] for p in page.context["base_choices"]]
        self.assertEqual(choices[:2], ["ages", "ages_big"])
        self.assertTrue({"ages_blitz", "ages_settlers", "ages_explorer", "settlers", "explorer", "friendly",
                         "classic"} <= set(choices))
        self.assertContains(page, 'data-base-choice="explorer"')
        self.assertNotContains(page, "Experimental rules")
        self.assertNotContains(page, "code-box")
        features = {g["key"]: {row["setting"].path for sec in g["sections"] for row in sec["rows"]}
                    for g in page.context["feature_editors"]}
        self.assertEqual(list(features), ["ages", "settlers", "visibility"])
        self.assertIn("ages.age2.cost", features["ages"])
        self.assertIn("settlers.builder_required", features["settlers"])
        self.assertIn("visibility.map", features["visibility"])
        others = {row["setting"].path for g in page.context["editor"] for sec in g["sections"] for row in sec["rows"]}
        self.assertIn("robber.fish_ransom", others)
        self.assertFalse(set().union(*features.values()) & others)

    def test_custom_game_from_an_experimental_type(self):
        self.client.force_login(self.bo)
        data = settings_form_data("classic", {"players": {"max": 4}})
        data.update({"base": "explorer", "s:robber.fish_ransom": "3"})
        self.client.post(reverse("lobby:list"), data)
        game = Game.objects.order_by("-pk").first()
        settings = load_preset(game.preset, game.overrides)
        self.assertEqual(game.preset, "explorer")
        self.assertEqual((settings.visibility.map.value, settings.settlers.builder_required.value), ("explored", "always"))
        self.assertEqual(settings.robber.fish_ransom, 3)
        self.assertFalse(self.client.post(reverse("lobby:list"), {"preset": "explorer", "max_players": "4"})
                         .context["form"].is_valid())

    def test_same_name_replaces_and_delete(self):
        services.save_settings(self.bo, "x", "classic", {})
        services.save_settings(self.bo, "x", "blitz", {})
        self.assertEqual(SavedSettings.objects.get(owner=self.bo).preset, "blitz")
        saved = SavedSettings.objects.get()
        self.client.force_login(self.host)  # not the owner
        self.client.post(reverse("lobby:delete_saved", args=[saved.pk]))
        self.assertTrue(SavedSettings.objects.exists())
        self.client.force_login(self.bo)
        self.client.post(reverse("lobby:delete_saved", args=[saved.pk]))
        self.assertFalse(SavedSettings.objects.exists())
        with self.assertRaises(LobbyError):
            services.save_settings(self.bo, "   ", "classic", {})


class ChangeSettingsTests(TestCase):
    def setUp(self):
        self.host, self.bo = user("ana"), user("bo")
        self.game = services.create_game(self.host, "classic", {"players": {"max": 4}})
        services.join_game(self.game, self.bo)
        services.set_ready(self.game, self.bo, True)
        self.url = reverse("lobby:edit_settings", args=[self.game.code])

    def test_page_shows_current_settings(self):
        services.change_settings(self.game, self.host, "blitz", {"players": {"max": 4}, "victory": {"target": 6}})
        self.client.force_login(self.host)
        page = self.client.get(self.url)
        self.assertContains(page, 'name="target"')
        self.assertEqual(page.context["form"].data["target"], "6")
        self.assertEqual(page.context["form"].data["base"], "blitz")

    def test_host_changes_and_players_get_ready_again(self):
        self.client.force_login(self.host)
        response = self.client.post(self.url, {"preset": "custom", "base": "blitz", "max_players": "4",
                                               "robber": "on", "spare_setup": "on", "target": "8"})
        self.assertRedirects(response, reverse("lobby:detail", args=[self.game.code]))
        self.game.refresh_from_db()
        self.assertEqual((self.game.preset, self.game.overrides["victory"]), ("blitz", {"target": 8}))
        self.assertFalse(GamePlayer.objects.get(user=self.bo).ready)

    def test_only_host_and_seats_must_fit(self):
        self.client.force_login(self.bo)
        self.assertRedirects(self.client.get(self.url), reverse("lobby:detail", args=[self.game.code]))
        services.add_bot(self.game, self.host, "easy")
        with self.assertRaises(LobbyError) as ctx:
            services.change_settings(self.game, self.host, "classic", {"players": {"max": 2}})
        self.assertEqual(ctx.exception.code, "lobby.too_many_seated")
        with self.assertRaises(LobbyError):
            services.change_settings(self.game, self.bo, "classic", {"players": {"max": 4}})
        self.assertEqual(Game.objects.get().overrides, {"players": {"max": 4}})


class GrowingSightTests(TestCase):
    def test_explorer_uses_explored_sight_and_the_game_page_says_so(self):
        host = user("ana")
        game = services.create_game(host, "explorer", {"players": {"max": 4}})
        self.assertEqual(load_preset(game.preset, game.overrides).visibility.map.value, "explored")
        self.client.force_login(host)
        page = self.client.get(reverse("lobby:detail", args=[game.code]))
        self.assertContains(page, "Explored")
        huge = services.create_game(host, "huge", {"players": {"max": 8}})
        self.assertEqual(load_preset(huge.preset, huge.overrides).visibility.map.value, "open")
        self.assertNotContains(self.client.get(reverse("lobby:detail", args=[huge.code])), "Explored")

    def test_custom_game_can_turn_on_growing_sight_and_hidden_numbers(self):
        host = user("bo")
        self.client.force_login(host)
        data = settings_form_data("classic", {"players": {"max": 4}})
        data.update({"s:visibility.map": "growing", "s:visibility.hidden_numbers": "1"})
        self.client.post(reverse("lobby:list"), data)
        game = Game.objects.get()
        settings = load_preset(game.preset, game.overrides)
        self.assertEqual(settings.visibility.map.value, "growing")
        self.assertTrue(settings.visibility.hidden_numbers)
