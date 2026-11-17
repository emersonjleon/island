from django.contrib import admin

from .models import ChatMessage, ChatSettings, Friendship, SocialMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("game", "name", "text", "created_at")
    search_fields = ("game__code", "name", "text")
    raw_id_fields = ("game", "user")


@admin.register(SocialMessage)
class SocialMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "recipient", "text", "created_at")
    search_fields = ("name", "text")
    raw_id_fields = ("sender", "recipient")


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "accepted", "created_at")
    raw_id_fields = ("from_user", "to_user")


@admin.register(ChatSettings)
class ChatSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "privacy")
    raw_id_fields = ("user",)
