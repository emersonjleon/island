"""Every app's URLs are included here up front, so later packages only edit their own urls.py."""
from django.contrib import admin
from django.urls import include, path

from common.views import home, how_to_play, how_to_play_variations

urlpatterns = [
    path("", home, name="home"),
    path("how-to-play/", how_to_play, name="how_to_play"),
    path("how-to-play/variations/", how_to_play_variations, name="how_to_play_variations"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("lobby/", include("lobby.urls")),
    path("play/", include("gameplay.urls")),
]
