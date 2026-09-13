"""WebSocket authentication middleware.

Browsers can't set custom headers (like `Authorization: Bearer ...`) on a
WebSocket handshake, so the access JWT travels as a `?token=` query param
instead - the standard workaround for JWT-over-WebSocket. This validates it
with the same SimpleJWT `AccessToken` class the REST API already issues, so
it accepts exactly the tokens `POST /api/v1/auth/...` hands out (no session
auth, no separate credential system).
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _resolve_user(token: str):
    from apps.accounts.models import User

    try:
        validated = AccessToken(token)
        return User.objects.get(pk=validated["user_id"], is_active=True)
    except (TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        token = parse_qs(query_string).get("token", [None])[0]
        scope["user"] = await _resolve_user(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
