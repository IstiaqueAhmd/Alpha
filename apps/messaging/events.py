"""Fan-out of chat events to connected WebSocket clients.

Each consumer joins one Channels group, ``user_<id>`` (see
`consumers.ChatConsumer.connect`), covering every tab/device a user has
open - so notifying a conversation just means `group_send` to each
participant's group, with no per-conversation group to keep in sync as
members change.

A dropped real-time event should never fail the REST call that triggered
it, so a missing channel layer is a silent no-op here rather than raising.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_to_users(user_ids, event_type: str, data: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    for user_id in {uid for uid in user_ids if uid is not None}:
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {"type": "chat.event", "event": event_type, "data": data},
        )
