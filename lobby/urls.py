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
    path("<str:code>/bots/add/", views.add_bot, name="add_bot"),
    path("<str:code>/bots/remove/", views.remove_bot, name="remove_bot"),
    path("<str:code>/start/", views.start, name="start"),
    path("<str:code>/settings/", views.edit_settings, name="edit_settings"),
    path("<str:code>/settings/save/", views.save_game_settings, name="save_settings"),
    path("saved/<int:saved_id>/delete/", views.delete_saved, name="delete_saved"),
    path("<str:code>/cancel/", views.cancel, name="cancel"),
    path("<str:code>/again/", views.play_again, name="play_again"),
]
