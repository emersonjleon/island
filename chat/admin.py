from django.contrib import admin

from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("game", "name", "text", "created_at")
    search_fields = ("game__code", "name", "text")
    raw_id_fields = ("game", "user")
