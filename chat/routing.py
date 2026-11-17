from django.urls import path

from .consumers import SocialConsumer

websocket_urlpatterns = [
    path("ws/social/", SocialConsumer.as_asgi()),
]
