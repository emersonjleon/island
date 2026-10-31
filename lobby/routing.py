from django.urls import path

from .consumers import LobbyConsumer

websocket_urlpatterns = [
    path("ws/lobby/<str:code>/", LobbyConsumer.as_asgi()),
]
