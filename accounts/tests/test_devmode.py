from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import devmode
from accounts.models import User
from chat.models import Channel, ChannelKind, Friendship, Message
from lobby.models import Game, GamePlayer, GameStatus

PASSWORD = "tidal-basalt-91"
DEVS = ["emersonleon", "emer2"]


def make_user(username: str, **extra) -> User:
    return User.objects.create_user(username, f"{username}@example.com", PASSWORD, **extra)


def make_game(host: User, status: str = GameStatus.LOBBY, **fields) -> Game:
    game = Game.objects.create(host=host, status=status, **fields)
    GamePlayer.objects.create(game=game, user=host, colour="red")
    return game


@override_settings(DEVELOPER_USERNAMES=DEVS)
class AccessTests(TestCase):
    def test_developers_by_username(self):
        self.assertTrue(make_user("emersonleon").is_developer)
        self.assertTrue(make_user("Emer2").is_developer)
        self.assertFalse(make_user("ana").is_developer)
        self.assertFalse(make_user("emer3").is_developer)

    def test_inactive_developer_is_not_a_developer(self):
        self.assertFalse(make_user("emer2", is_active=False).is_developer)

    def test_anonymous_is_sent_to_login(self):
        for name in ("accounts:dev_overview", "accounts:dev_users"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("accounts:login"), response["Location"])

    def test_other_users_get_404(self):
        make_user("ana")
        self.client.login(username="ana", password=PASSWORD)
        for name in ("accounts:dev_overview", "accounts:dev_users"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 404)

    def test_staff_who_is_not_listed_gets_404(self):
        make_user("boss", is_staff=True, is_superuser=True)
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("accounts:dev_overview")).status_code, 404)

    def test_nav_link_only_for_developers(self):
        make_user("ana")
        self.client.login(username="ana", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("home")), reverse("accounts:dev_overview"))
        make_user("emersonleon")
        self.client.login(username="emersonleon", password=PASSWORD)
        self.assertContains(self.client.get(reverse("home")), reverse("accounts:dev_overview"))


@override_settings(DEVELOPER_USERNAMES=DEVS)
class PanelTests(TestCase):
    def setUp(self):
        self.dev = make_user("emersonleon")
        self.ana = make_user("ana", display_name="Ana")
        self.ben = make_user("ben")
        now = timezone.now()
        finished = make_game(self.ana, GameStatus.FINISHED, started_at=now - timedelta(minutes=30), finished_at=now)
        GamePlayer.objects.create(game=finished, bot_level="easy", bot_name="Ada", colour="blue")
        GamePlayer.objects.filter(game=finished, user=self.ana).update(is_winner=True, final_points=10)
        running = make_game(self.ben, GameStatus.RUNNING)
        GamePlayer.objects.create(game=running, user=self.ana, colour="blue")
        make_game(self.ana)
        channel = Channel.objects.create(kind=ChannelKind.PUBLIC, key="public:es")
        Message.objects.create(channel=channel, sender=self.ana, name="Ana", text="hola")
        Message.objects.create(channel=channel, sender=self.ben, name="ben", text="hi")
        Friendship.objects.create(from_user=self.ana, to_user=self.ben, accepted=True)
        self.client.login(username="emersonleon", password=PASSWORD)

    def test_overview_numbers(self):
        data = devmode.overview()
        self.assertEqual(data["users"]["total"], 3)
        self.assertEqual(data["users"]["never_played"], 1)  # the developer
        games = data["games"]
        self.assertEqual((games["total"], games["finished"], games["running"], games["waiting"]), (3, 1, 1, 1))
        self.assertEqual(games["playing_now"], 2)
        self.assertEqual(games["avg_minutes"], 30)
        self.assertEqual(games["bot_seats"], 1)
        self.assertEqual(games["human_seats"], 4)
        self.assertEqual(data["chat"]["total"], 2)
        self.assertEqual(data["chat"]["friends"], 1)
        self.assertEqual(data["per_day"][-1].count, 3)
        self.assertEqual(data["per_day"][-1].percent, 100)
        self.assertEqual(data["top_players"][0].username, "ana")
        self.assertEqual((data["top_players"][0].games, data["top_players"][0].wins), (3, 1))

    def test_overview_page(self):
        response = self.client.get(reverse("accounts:dev_overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ana@example.com")
        self.assertContains(response, Game.objects.first().code)

    def test_overview_in_spanish(self):
        self.dev.preferred_language = "es"
        self.dev.save()
        response = self.client.get(reverse("accounts:dev_overview"), HTTP_ACCEPT_LANGUAGE="es")
        self.assertEqual(response.status_code, 200)

    def test_users_search_and_sort(self):
        response = self.client.get(reverse("accounts:dev_users"), {"q": "an"})
        self.assertEqual([u.username for u in response.context["page"].object_list], ["ana"])
        for sort in list(devmode.USER_SORTS) + ["bogus"]:
            response = self.client.get(reverse("accounts:dev_users"), {"sort": sort})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page"].paginator.count, 3)
        response = self.client.get(reverse("accounts:dev_users"), {"sort": "games"})
        self.assertEqual(response.context["page"].object_list[0].username, "ana")

    def test_empty_platform(self):
        Game.objects.all().delete()
        Message.objects.all().delete()
        data = devmode.overview()
        self.assertIsNone(data["games"]["avg_minutes"])
        self.assertEqual(self.client.get(reverse("accounts:dev_overview")).status_code, 200)
