"""Online/offline presence, tracked by active WebSocket connection count.

A user can have several connections open (multiple tabs/devices), so
presence is a *counter*, not a boolean - only offline once it hits zero.
`InMemoryPresenceBackend` is process-local (default, no infra needed);
`RedisPresenceBackend` is correct across multiple worker processes - switch
via `CHAT_PRESENCE_BACKEND = "redis"` once Redis is available.
"""

from __future__ import annotations

import threading
from collections import Counter

from django.conf import settings


class InMemoryPresenceBackend:
    def __init__(self) -> None:
        self._counts: Counter[int] = Counter()
        self._lock = threading.Lock()

    def connect(self, user_id: int) -> int:
        with self._lock:
            self._counts[user_id] += 1
            return self._counts[user_id]

    def disconnect(self, user_id: int) -> int:
        with self._lock:
            if self._counts[user_id] > 0:
                self._counts[user_id] -= 1
            count = self._counts[user_id]
            if count <= 0:
                del self._counts[user_id]
            return max(count, 0)

    def is_online(self, user_id: int) -> bool:
        with self._lock:
            return self._counts.get(user_id, 0) > 0

    def online_user_ids(self, user_ids) -> set[int]:
        with self._lock:
            return {uid for uid in user_ids if self._counts.get(uid, 0) > 0}


class RedisPresenceBackend:
    KEY_PREFIX = "chat:presence:"

    def __init__(self) -> None:
        import redis  # local import: only required when this backend is selected

        self._client = redis.Redis.from_url(settings.CHAT_PRESENCE_REDIS_URL)

    def _key(self, user_id: int) -> str:
        return f"{self.KEY_PREFIX}{user_id}"

    def connect(self, user_id: int) -> int:
        return int(self._client.incr(self._key(user_id)))

    def disconnect(self, user_id: int) -> int:
        key = self._key(user_id)
        new_value = int(self._client.decr(key))
        if new_value <= 0:
            # Clamp at 0 and drop the key rather than let it go negative
            # (e.g. a disconnect racing a process restart that lost state).
            self._client.delete(key)
            return 0
        return new_value

    def is_online(self, user_id: int) -> bool:
        value = self._client.get(self._key(user_id))
        return bool(value) and int(value) > 0

    def online_user_ids(self, user_ids) -> set[int]:
        user_ids = list(user_ids)
        if not user_ids:
            return set()
        values = self._client.mget([self._key(uid) for uid in user_ids])
        return {uid for uid, value in zip(user_ids, values) if value and int(value) > 0}


_backend = None
_backend_lock = threading.Lock()


def get_presence_backend():
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                if getattr(settings, "CHAT_PRESENCE_BACKEND", "memory") == "redis":
                    _backend = RedisPresenceBackend()
                else:
                    _backend = InMemoryPresenceBackend()
    return _backend


class PresenceService:
    """Facade so callers never touch the backend classes directly."""

    @staticmethod
    def connect(user_id: int) -> int:
        return get_presence_backend().connect(user_id)

    @staticmethod
    def disconnect(user_id: int) -> int:
        return get_presence_backend().disconnect(user_id)

    @staticmethod
    def is_online(user_id: int) -> bool:
        return get_presence_backend().is_online(user_id)

    @staticmethod
    def online_user_ids(user_ids) -> set[int]:
        return get_presence_backend().online_user_ids(user_ids)
