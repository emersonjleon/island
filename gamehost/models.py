from django.db import models

from lobby.models import Game


class GameSnapshot(models.Model):
    """A full engine state (``engine.codec.dump``). Restore = latest snapshot + later commands."""

    class Kind(models.TextChoices):
        START = "start"
        ROLL = "roll"
        END = "end"
        SHUTDOWN = "shutdown"

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="snapshots")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    cmd_seq = models.PositiveIntegerField(help_text="Commands 1..cmd_seq are included in this state.")
    game_ms = models.BigIntegerField()
    state = models.JSONField()
    state_hash = models.CharField(max_length=64)
    # Per-audience event sequence numbers ({"0": 12, "spect": 9}) so clients keep counting after a restore.
    seqs = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["game", "-cmd_seq", "-id"]
        indexes = [models.Index(fields=["game", "-cmd_seq"])]


class GameCommand(models.Model):
    """Append-only log of accepted commands, in the order the engine applied them."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="commands")
    cmd_seq = models.PositiveIntegerField()
    game_ms = models.BigIntegerField()
    seat = models.PositiveSmallIntegerField()
    payload = models.JSONField()

    class Meta:
        ordering = ["game", "cmd_seq"]
        constraints = [models.UniqueConstraint(fields=["game", "cmd_seq"], name="gamehost_unique_cmd_seq")]
