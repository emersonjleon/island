from django.contrib import admin

from .models import Game, GamePlayer


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
