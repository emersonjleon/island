from django.urls import path

from . import views

app_name = "lobby"

urlpatterns = [
    path("", views.game_list, name="list"),
    path("<str:code>/", views.game_detail, name="detail"),
    path("<str:code>/seats/", views.game_seats, name="seats"),
    path("<str:code>/join/", views.join, name="join"),
    path("<str:code>/leave/", views.leave, name="leave"),
    path("<str:code>/colour/", views.colour, name="colour"),
    path("<str:code>/ready/", views.ready, name="ready"),
    path("<str:code>/start/", views.start, name="start"),
    path("<str:code>/cancel/", views.cancel, name="cancel"),
]
