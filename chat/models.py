"""Every conversation on the site is a ``Channel`` with ``Message`` rows.

* ``public`` - one room per language ("public:es"), for everyone whose privacy allows it;
* ``game``   - one per game ("game:42"), from the waiting room into the game; goes with the game;
* ``direct`` - one per pair of people ("dm:3:8"), with a ``Membership`` for each holding what they read.

One table of messages, indexed by (channel, id), keeps history paging, unread counts,
retention and moderation the same for every kind; see docs/CHAT.md.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from lobby.models import Game


class ChannelKind(models.TextChoices):
    PUBLIC = "public", _("Public room")
    GAME = "game", _("Game")
    DIRECT = "direct", _("Private conversation")


class Channel(models.Model):
    kind = models.CharField(max_length=16, choices=ChannelKind.choices)
    # Stable name: "public:<lang>", "game:<game id>", "dm:<low user id>:<high user id>".
    key = models.CharField(max_length=64, unique=True)
    game = models.OneToOneField(Game, on_delete=models.CASCADE, null=True, blank=True, related_name="chat_channel")
    # Id of the newest message, so conversation lists sort without scanning messages.
    last_message_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.key


class Membership(models.Model):
    """Someone in a channel that has a fixed list of people (private conversations)."""

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_memberships")
    # Messages up to this id have been read; the rest count as unread.
    last_read_id = models.BigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["channel", "user"], name="chat_membership_unique")]
        indexes = [models.Index(fields=["user", "channel"], name="chat_membership_user")]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.channel_id}"


class Message(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="chat_messages")
    # Copied when the line is written, so the history reads the same later.
    name = models.CharField(max_length=64)
    colour = models.CharField(max_length=16, blank=True)  # game channels: the writer's seat colour
    seat = models.PositiveSmallIntegerField(null=True, blank=True)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["channel", "id"], name="chat_message_channel")]

    def __str__(self) -> str:
        return f"{self.channel_id}:{self.name}: {self.text[:30]}"


class Privacy(models.TextChoices):
    """Who may write to someone outside a game. The game chat is never affected."""

    EVERYONE = "everyone", _("Everyone: public chat and messages from anyone")
    FRIENDS = "friends", _("Only friends: messages from friends, no public chat")
    GAMES = "games", _("Only in games: no public chat or private messages")


class ChatSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True,
                                related_name="chat_settings")
    privacy = models.CharField(max_length=16, choices=Privacy.choices, default=Privacy.EVERYONE)
    # Language of the public room; blank follows the person's language.
    room = models.CharField(max_length=10, blank=True)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.privacy}"


class Friendship(models.Model):
    """A friend request from ``from_user`` to ``to_user``; once accepted they are friends both ways."""

    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_sent")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_received")
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="chat_friendship_unique"),
            models.CheckConstraint(condition=~models.Q(from_user=models.F("to_user")), name="chat_friendship_not_self"),
        ]
        indexes = [models.Index(fields=["to_user", "accepted"], name="chat_friendship_to")]

    def __str__(self) -> str:
        return f"{self.from_user_id} -> {self.to_user_id}{' (friends)' if self.accepted else ''}"
