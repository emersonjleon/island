from django.urls import path

from . import views

app_name = "gameplay"

urlpatterns = [
    path("<str:code>/", views.play, name="play"),
]
