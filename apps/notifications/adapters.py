from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger(__name__)


class NotificationAdapter(ABC):
    """A delivery channel for an already-persisted Notification.

    The Notification row is always written first (it's the source of truth
    for the paginated list / read-status API), then each requested channel's
    adapter delivers it onward. New channels (push, SMS, ...) just implement
    `deliver` and register in `ADAPTERS` - nothing else in this app changes.
    """

    @abstractmethod
    def deliver(self, notification: Notification) -> None: ...


class InAppAdapter(NotificationAdapter):
    """No-op: the Notification row itself *is* the in-app delivery."""

    def deliver(self, notification: Notification) -> None:
        return None


class EmailAdapter(NotificationAdapter):
    """Emails the recipient the notification's title/message.

    Best-effort: this rides along an in-app notification that has already
    been persisted, so a mail failure here is logged rather than raised -
    unlike apps.teams.emails.send_invitation_email, which is the primary
    (and only) delivery for its message and is allowed to fail loudly.
    """

    def deliver(self, notification: Notification) -> None:
        recipient_email = notification.recipient.email
        if not recipient_email:
            return
        try:
            send_mail(
                subject=notification.title,
                message=notification.message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception:
            logger.exception(
                "EmailAdapter failed to deliver notification %s", notification.id
            )


ADAPTERS: dict[str, NotificationAdapter] = {
    "in_app": InAppAdapter(),
    "email": EmailAdapter(),
}
