from __future__ import annotations

from typing import Iterable

from django.db.models import QuerySet
from django.utils import timezone

from . import exceptions as exc
from .adapters import ADAPTERS
from .models import Notification


class NotificationService:
    """Create and read notifications. The in-app row is always written;
    other channels (email, ...) are opt-in via `channels` and never affect
    whether the in-app notification exists.
    """

    @staticmethod
    def notify(
        *,
        recipient,
        notification_type: str,
        title: str,
        message: str = "",
        data: dict | None = None,
        channels: tuple[str, ...] = ("in_app",),
    ) -> Notification:
        notification = Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data or {},
        )
        for channel in channels:
            adapter = ADAPTERS.get(channel)
            if adapter is not None:
                adapter.deliver(notification)
        return notification

    @staticmethod
    def notify_many(
        *,
        recipients: Iterable,
        notification_type: str,
        title: str,
        message: str = "",
        data: dict | None = None,
        channels: tuple[str, ...] = ("in_app",),
        batch_size: int = 500,
    ) -> list[Notification]:
        """Same as `notify`, one row per recipient, same title/message/data
        for all of them (e.g. "team member added" fanned out to a team).

        `batch_size` caps how many rows go into a single INSERT so a
        platform-wide broadcast doesn't become one unbounded query. It does
        NOT make this safe for a synchronous "email everyone" broadcast -
        `channels` other than "in_app" still deliver one at a time, in this
        request, with no queue behind them.
        """
        notifications = Notification.objects.bulk_create(
            [
                Notification(
                    recipient=recipient,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    data=data or {},
                )
                for recipient in recipients
            ],
            batch_size=batch_size,
        )
        for notification in notifications:
            for channel in channels:
                adapter = ADAPTERS.get(channel)
                if adapter is not None:
                    adapter.deliver(notification)
        return notifications

    @staticmethod
    def list_for(user) -> QuerySet[Notification]:
        return Notification.objects.filter(recipient=user)

    @staticmethod
    def mark_read(*, user, notification_id: int) -> Notification:
        try:
            notification = Notification.objects.get(pk=notification_id, recipient=user)
        except Notification.DoesNotExist:
            raise exc.NotificationNotFound()

        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at", "updated_at"])
        return notification

    @staticmethod
    def mark_all_read(*, user) -> int:
        return Notification.objects.filter(
            recipient=user, read_at__isnull=True
        ).update(read_at=timezone.now())
