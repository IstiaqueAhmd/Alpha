from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Notification(TimeStampedModel):
    """A single in-app notification for one recipient.

    `notification_type` is a free-text producer-defined tag (e.g.
    "team.invitation_received"), not a fixed choices set - each app that
    raises notifications owns its own type strings so this app never needs
    editing to support a new source model. `data` carries whatever payload
    the frontend needs to route/render the notification (ids, names) without
    an extra query.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "read_at"]),
            models.Index(fields=["recipient", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.notification_type} -> {self.recipient_id}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
