from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from accounts.models import User
from chat import services, social
from chat.models import Message
from lobby import services as lobby


class PruneTests(TestCase):
    def test_only_old_public_lines_go(self):
        ana, bo = User.objects.create_user("ana"), User.objects.create_user("bo")
        game = lobby.create_game(ana, "classic", {"players": {"max": 3}})
        social.post_public(ana, "old")
        social.post_public(ana, "new")
        social.post_dm(ana, bo, "private")
        services.post(game.pk, ana, "in game")
        Message.objects.exclude(text="new").update(created_at=timezone.now() - timedelta(days=40))
        out = StringIO()
        call_command("prune_chat", stdout=out)
        self.assertEqual(sorted(Message.objects.values_list("text", flat=True)), ["in game", "new", "private"])
        self.assertIn("Deleted 1", out.getvalue())


class GameChatMigrationTests(TransactionTestCase):
    """0002 moves the game chats of 0001 (one ChatMessage table) into game channels."""

    before = [("chat", "0001_initial")]
    after = [("chat", "0002_channels")]

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_lines_keep_their_order_seat_and_time(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps
        user = old.get_model("accounts", "User").objects.create(username="ana")
        game = old.get_model("lobby", "Game").objects.create(code="ABCDE", host=user, preset="classic")
        ChatMessage = old.get_model("chat", "ChatMessage")
        first = ChatMessage.objects.create(game=game, user=user, name="ana", colour="red", seat=0, text="hola")
        ChatMessage.objects.create(game=game, user=None, name="eve", text="gg")
        when = timezone.now() - timedelta(days=3)
        ChatMessage.objects.filter(pk=first.pk).update(created_at=when)

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps
        channel = new.get_model("chat", "Channel").objects.get()
        self.assertEqual((channel.key, channel.kind, channel.game_id), (f"game:{game.pk}", "game", game.pk))
        rows = list(new.get_model("chat", "Message").objects.filter(channel=channel).order_by("id"))
        self.assertEqual([(m.name, m.colour, m.seat, m.text, m.sender_id) for m in rows],
                         [("ana", "red", 0, "hola", user.pk), ("eve", "", None, "gg", None)])
        self.assertEqual(rows[0].created_at, when)
        self.assertEqual(channel.last_message_id, rows[-1].id)
