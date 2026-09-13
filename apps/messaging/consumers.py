from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from .events import broadcast_to_users
from .models import ConversationMember
from .presence import PresenceService


class ChatConsumer(JsonWebsocketConsumer):
    """One connection per browser tab / device, authenticated by
    `apps.messaging.ws_auth.JWTAuthMiddleware`.

    Push-only: the client never sends business messages here. Sending,
    editing, deleting a message, marking read, managing group membership -
    all of that goes through the REST API in `apps.messaging.views` (which
    calls into `apps.messaging.services`), and *that* code broadcasts the
    result via `events.broadcast_to_users`. This consumer's only job is to
    authenticate, track presence, and relay those broadcasts to the client.
    """

    def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            self.close(code=4401)
            return

        self.user_id = user.id
        self.group_name = f"user_{self.user_id}"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

        # Only the *first* connection for this user is a 0->1 transition -
        # a second tab/device opening shouldn't re-announce "online".
        if PresenceService.connect(self.user_id) == 1:
            self._broadcast_presence(is_online=True)

    def disconnect(self, code):
        if not hasattr(self, "user_id"):
            return
        async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)
        # Symmetrically, only announce "offline" once the *last* connection closes.
        if PresenceService.disconnect(self.user_id) == 0:
            self._broadcast_presence(is_online=False)

    def _broadcast_presence(self, *, is_online: bool) -> None:
        partner_ids = (
            ConversationMember.objects
            .filter(conversation__memberships__user_id=self.user_id)
            .exclude(user_id=self.user_id)
            .values_list("user_id", flat=True)
            .distinct()
        )
        broadcast_to_users(partner_ids, "presence.update", {"user_id": self.user_id, "is_online": is_online})

    def chat_event(self, event):
        """Channels dispatches a `group_send({"type": "chat.event", ...})`
        to this method by name (`.` -> `_`). Unwrap it into the
        `{"type": ..., "data": ...}` shape the client actually sees.
        """
        self.send_json({"type": event["event"], "data": event["data"]})
