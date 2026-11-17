from django.conf import settings
from django.db import models

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
