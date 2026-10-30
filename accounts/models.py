from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


def default_language() -> str:
    return settings.LANGUAGE_CODE


class User(AbstractUser):
    display_name = models.CharField(_("display name"), max_length=40, blank=True)
    preferred_language = models.CharField(
        _("language"), max_length=10, choices=settings.LANGUAGES, default=default_language
    )
    # Action name -> list of key combos, e.g. {"build_road": ["KeyR"]}. Empty = client defaults.
    keybindings = models.JSONField(_("key bindings"), default=dict, blank=True)
    # Client preferences such as {"renderer": "2d", "palette": "default"}.
    ui_prefs = models.JSONField(_("interface preferences"), default=dict, blank=True)

    @property
    def public_name(self) -> str:
        return self.display_name or self.username
