import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# No 0/O, 1/I/L: codes are read aloud and typed by players.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 5

# Player colours offered in the lobby, in seat-picking order. The engine only stores the name.
COLOURS = [
    ("red", _("Red")),
    ("blue", _("Blue")),
    ("white", _("White")),
    ("orange", _("Orange")),
    ("green", _("Green")),
    ("brown", _("Brown")),
]
COLOUR_VALUES = [c for c, _label in COLOURS]


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class GameStatus(models.TextChoices):
    LOBBY = "LOBBY", _("Waiting for players")
    STARTING = "STARTING", _("Starting")
    RUNNING = "RUNNING", _("Running")
    FINISHED = "FINISHED", _("Finished")
    ABORTED = "ABORTED", _("Cancelled")


class Game(models.Model):
    code = models.CharField(max_length=CODE_LENGTH, unique=True, editable=False)
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="hosted_games")
    status = models.CharField(max_length=10, choices=GameStatus.choices, default=GameStatus.LOBBY, db_index=True)
    preset = models.CharField(max_length=32, default="classic")
    # What the host chose on top of the preset (differences only).
    overrides = models.JSONField(default=dict, blank=True)
    # The full validated settings, written at start; empty while in the lobby.
    settings = models.JSONField(default=dict, blank=True)
    settings_schema_version = models.PositiveIntegerField(null=True, blank=True)
    seed = models.BigIntegerField(null=True, blank=True)
    engine_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._unused_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _unused_code() -> str:
        while True:
            code = new_code()
            if not Game.objects.filter(code=code).exists():
                return code

    @property
    def group_name(self) -> str:
        return f"lobby.{self.code}"

    @property
    def is_open(self) -> bool:
        return self.status == GameStatus.LOBBY


class GamePlayer(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_seats")
    # Assigned at start (0..n-1, following settings.players.seat_order); null in the lobby.
    seat = models.PositiveSmallIntegerField(null=True, blank=True)
    colour = models.CharField(max_length=16, choices=COLOURS)
    ready = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    final_points = models.PositiveSmallIntegerField(null=True, blank=True)
    is_winner = models.BooleanField(default=False)

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["game", "user"], name="lobby_one_seat_per_user"),
            models.UniqueConstraint(fields=["game", "colour"], name="lobby_unique_colour"),
            models.UniqueConstraint(
                fields=["game", "seat"], condition=models.Q(seat__isnull=False), name="lobby_unique_seat"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.game.code}:{self.user}"
