from django.urls import path
from .consumers import InterviewSignalingConsumer

websocket_urlpatterns = [
    path(
        "ws/interviews/<int:interview_id>/",
        InterviewSignalingConsumer.as_asgi(),
    ),
]