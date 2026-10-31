"""Every app's URLs are included here up front, so later packages only edit their own urls.py."""
from django.contrib import admin
from django.urls import include, path

from common.views import home

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("lobby/", include("lobby.urls")),
    path("play/", include("gameplay.urls")),
]
