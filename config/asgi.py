import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()


ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import OriginValidator
from django.conf import settings

from interviews.routing import websocket_urlpatterns


application = ProtocolTypeRouter({
    "http": django_asgi_app,

    "websocket": OriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
        settings.WS_ALLOWED_ORIGINS or ["*"],
    ),
})