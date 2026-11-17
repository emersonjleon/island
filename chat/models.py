from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from lobby.models import Game


class ChatMessage(models.Model):
    """One line of a game's chat. The same conversation runs from the waiting room into the game."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="chat_messages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    # Copied when the line is written, so the history reads the same later.
    name = models.CharField(max_length=64)
    colour = models.CharField(max_length=16, blank=True)
    seat = models.PositiveSmallIntegerField(null=True, blank=True)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["game", "id"], name="chat_game_id")]

    def __str__(self) -> str:
        return f"{self.game_id}:{self.name}: {self.text[:30]}"


class Privacy(models.TextChoices):
    """Who may write to someone outside a game. The game chat is never affected."""

    EVERYONE = "everyone", _("Everyone: public chat and messages from anyone")
    FRIENDS = "friends", _("Only friends: messages from friends, no public chat")
    GAMES = "games", _("Only in games: no public chat or private messages")


class ChatSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True,
                                related_name="chat_settings")
    privacy = models.CharField(max_length=16, choices=Privacy.choices, default=Privacy.EVERYONE)

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

    def __str__(self) -> str:
        return f"{self.from_user_id} -> {self.to_user_id}{' (friends)' if self.accepted else ''}"


class SocialMessage(models.Model):
    """A line of the site-wide chat: public when ``recipient`` is empty, otherwise a private message."""

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_sent")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                  related_name="social_received")
    name = models.CharField(max_length=64)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["recipient", "id"], name="chat_social_recipient"),
            models.Index(fields=["sender", "id"], name="chat_social_sender"),
        ]

    def __str__(self) -> str:
        return f"{self.name} -> {self.recipient_id or 'all'}: {self.text[:30]}"
