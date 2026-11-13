import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings


# WebRTC signalling message types that are relayed to the other peer(s) in the room.
RELAY_TYPES = {
    "offer",
    "answer",
    "ice-candidate",
    "candidate",
    "chat",
    "media-state",
    "ready",
    "leave",
}


class InterviewSignalingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket signalling channel for WebRTC interviews.

    URL: ws://<host>/ws/interviews/<interview_id>/?token=<JWT access token>

    Flow:
      1. Client connects -> server sends {"type": "config", "iceServers": [...]}
      2. Peers already in the room get {"type": "peer-joined"}
         (they should then create and send an "offer").
      3. offer / answer / ice-candidate (and any other JSON) are relayed
         to the other peer(s) unchanged.
      4. When a peer disconnects the others get {"type": "peer-left"}.
    """

    async def connect(self):
        self.interview_id = self.scope["url_route"]["kwargs"]["interview_id"]

        self.room_group_name = f"interview_{self.interview_id}"

        self.user = await self._get_user()

        if getattr(settings, "WS_REQUIRE_AUTH", False) and self.user is None:
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

        # Give the browser its RTCPeerConnection ICE (STUN/TURN) servers.
        await self.send(
            text_data=json.dumps(
                {
                    "type": "config",
                    "iceServers": getattr(settings, "WEBRTC_ICE_SERVERS", []),
                    "user_id": self.user.id if self.user else None,
                }
            )
        )

        # Tell the peers already in the room that someone joined.
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "signal_message",
                "message": {
                    "type": "peer-joined",
                    "user_id": self.user.id if self.user else None,
                },
                "sender_channel": self.channel_name,
            },
        )

        print(f"Interview {self.interview_id}: WebSocket connected")

    async def disconnect(self, close_code):
        if not hasattr(self, "room_group_name"):
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "signal_message",
                "message": {
                    "type": "peer-left",
                    "user_id": self.user.id if self.user else None,
                },
                "sender_channel": self.channel_name,
            },
        )

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name,
        )

        print(f"Interview {self.interview_id}: WebSocket disconnected")

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return

        try:
            data = json.loads(text_data)

        except json.JSONDecodeError:
            await self.close(code=4000)
            return

        if not isinstance(data, dict):
            await self.close(code=4000)
            return

        # Simple keep-alive
        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
            return

        # Never let a client spoof server-side fields.
        data.pop("user_id", None)
        if self.user:
            data["user_id"] = self.user.id

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "signal_message",
                "message": data,
                "sender_channel": self.channel_name,
            },
        )

    async def signal_message(self, event):
        if event["sender_channel"] != self.channel_name:
            await self.send(
                text_data=json.dumps(event["message"])
            )

    async def _get_user(self):
        """Resolve the user from ?token=<JWT> (falls back to session auth)."""
        query = self.scope.get("query_string", b"").decode()
        token = None
        for part in query.split("&"):
            if part.startswith("token="):
                token = part[len("token="):]

        if token:
            try:
                return await sync_to_async(self._user_from_token)(token)
            except Exception:
                return None

        user = self.scope.get("user")
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        return None

    @staticmethod
    def _user_from_token(token):
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import AccessToken

        validated = AccessToken(token)
        return get_user_model().objects.get(id=validated["user_id"])
