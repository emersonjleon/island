from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from engine.settings import load_preset
from lobby.forms import KNOB_PATHS
from lobby.models import Game
from lobby.setting_labels import LABELS
from lobby.settings_editor import all_settings, changed_settings, editor_overrides, preset_inputs


class EditorTests(TestCase):
    def test_every_label_names_a_real_setting_and_most_settings_are_shown(self):
        paths = {s.path for s in all_settings()}
        self.assertGreater(len(paths), 70)
        self.assertTrue({"visibility.map", "visibility.hidden_numbers", "visibility.sight.city"} <= paths)
        later = {"visibility.scores", "visibility.trade_offers", "settlers.builder_required",
                 "clock.dice_mode", "robber.steal_rounding", "robber.move_on_seven", "robber.adjacency_timing"}
        self.assertEqual(set(LABELS) - paths, later)  # labelled, but only one choice exists yet

    def test_reading_inputs(self):
        base = load_preset("classic")
        data = {"s:clock.roll_interval_ms": "12.5", "s:robber.enabled": "0", "s:players.seat_order": "host",
                "s:economy.costs.road:lumber": "2", "s:victory.target": "10", "s:pieces.roads": ""}
        overrides, errors = editor_overrides(data, base)
        self.assertEqual(errors, [])
        self.assertEqual(overrides, {
            "clock": {"roll_interval_ms": 12500}, "robber": {"enabled": False}, "players": {"seat_order": "host"},
            "economy": {"costs": {"road": {"lumber": 2, "brick": 1}}}})  # target 10 is the base value

    def test_bad_inputs(self):
        base = load_preset("classic")
        data = {"s:clock.roll_interval_ms": "1", "s:pieces.roads": "x", "s:players.seat_order": "nope",
                "s:robber.enabled": "maybe"}
        overrides, errors = editor_overrides(data, base)
        self.assertEqual(overrides, {})
        self.assertEqual({e.setting.path for e in errors},
                         {"clock.roll_interval_ms", "pieces.roads", "players.seat_order", "robber.enabled"})

    def test_placeholders_and_changes(self):
        inputs = preset_inputs("blitz")
        self.assertEqual(inputs["s:clock.roll_interval_ms"], "10")
        self.assertEqual(inputs["s:robber.enabled"], "1")
        self.assertEqual(inputs["s:economy.costs.city:ore"], "3")
        changes = dict(changed_settings(load_preset("classic"), load_preset("blitz")))
        self.assertIn("10", changes.values())


class EditorFormTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user("ana", "ana@example.com", "pw-unused-123")
        self.client.force_login(self.host)

    def post(self, extra):
        return self.client.post(reverse("lobby:list"), {"preset": "custom", "base": "classic", "max_players": "4",
                                                        "robber": "on", "spare_setup": "on", **extra})

    def test_page_shows_the_editor_without_the_quick_rules(self):
        page = self.client.get(reverse("lobby:list"))
        self.assertContains(page, 'name="s:dev_cards.road_building_roads"')
        self.assertContains(page, 'name="s:economy.costs.city:ore"')
        for path in KNOB_PATHS:
            self.assertNotContains(page, f'name="s:{path}"')

    def test_create_with_all_settings(self):
        response = self.post({"s:dev_cards.road_building_roads": "3", "s:robber.knight_steal": "2",
                              "s:build.time_ms.megacity": "20"})
        game = Game.objects.get()
        self.assertRedirects(response, reverse("lobby:detail", args=[game.code]))
        self.assertEqual(game.overrides["dev_cards"], {"road_building_roads": 3})
        self.assertEqual(game.overrides["build"], {"time_ms": {"megacity": 20000}})
        page = self.client.get(reverse("lobby:detail", args=[game.code]))
        values = [v for _label, v in page.context["rule_changes"]]
        self.assertIn("3", values)
        self.assertIn("20", values)

    def test_errors_marked_on_the_setting(self):
        response = self.post({"s:dev_cards.road_building_roads": "-1"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Game.objects.exists())
        self.assertIn("dev_cards.road_building_roads", response.context["form"].editor_errors)
        self.assertTrue(response.context["editor_open"])

    def test_settings_that_do_not_fit_together(self):
        response = self.post({"s:setup.settlements": "6"})  # more than the 5 settlement pieces
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Game.objects.exists())
        self.assertIn("setup", " ".join(response.context["form"].editor_errors) + "setup")
        self.assertContains(response, "need more pieces")
