from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        (_("Game"), {"fields": ("display_name", "preferred_language", "keybindings", "ui_prefs")}),
    )
    list_display = ("username", "display_name", "email", "preferred_language", "is_staff")
