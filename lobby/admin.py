from django.contrib import admin

from .models import Game, GamePlayer, SavedSettings


class GamePlayerInline(admin.TabularInline):
    model = GamePlayer
    extra = 0


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("code", "host", "status", "preset", "created_at", "started_at")
    list_filter = ("status", "preset")
    search_fields = ("code", "host__username")
    readonly_fields = ("code",)
    inlines = [GamePlayerInline]


@admin.register(SavedSettings)
class SavedSettingsAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "preset", "updated_at")
    search_fields = ("name", "owner__username")
