from datetime import timedelta

from django.utils import timezone

from .models import User


class UpdateLastSeenMiddleware:
    """Update ``User.last_seen_at`` at most once per minute for authenticated requests."""

    UPDATE_INTERVAL = timedelta(minutes=1)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = timezone.now()
            if user.last_seen_at is None or (now - user.last_seen_at) >= self.UPDATE_INTERVAL:
                User.objects.filter(pk=user.pk).update(last_seen_at=now)
        return response
