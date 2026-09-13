from django.urls import re_path

from .consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(r"^api/v1/messaging/ws/chat/$", ChatConsumer.as_asgi()),
]
