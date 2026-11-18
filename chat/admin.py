from django.contrib import admin

from .models import Channel, ChatSettings, Friendship, Membership, Message


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("key", "kind", "last_message_id", "created_at")
    list_filter = ("kind",)
    search_fields = ("key",)
    raw_id_fields = ("game",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("channel", "name", "text", "created_at")
    list_filter = ("channel__kind",)
    search_fields = ("channel__key", "name", "text")
    raw_id_fields = ("channel", "sender")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("channel", "user", "last_read_id")
    raw_id_fields = ("channel", "user")


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "accepted", "created_at")
    raw_id_fields = ("from_user", "to_user")


@admin.register(ChatSettings)
class ChatSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "privacy", "room")
    raw_id_fields = ("user",)
