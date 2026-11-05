from django.contrib import admin

from .models import GameCommand, GameSnapshot


@admin.register(GameSnapshot)
class GameSnapshotAdmin(admin.ModelAdmin):
    list_display = ("game", "kind", "cmd_seq", "game_ms", "created_at")
    list_filter = ("kind",)
    exclude = ("state",)


@admin.register(GameCommand)
class GameCommandAdmin(admin.ModelAdmin):
    list_display = ("game", "cmd_seq", "game_ms", "seat")
