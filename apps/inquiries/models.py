import uuid
from django.conf import settings
from django.db import models
from apps.common.models import TimeStampedModel

def generate_uid() -> str:
    return uuid.uuid4().hex[:12]

class Inquiry(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    uid = models.CharField(max_length=12, default=generate_uid, unique=True, editable=False, db_index=True)

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_inquiries",
    )
    receiver_email = models.EmailField()
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_inquiries",
    )

    event_title = models.CharField(max_length=128)
    start_date_time = models.DateTimeField()
    expected_attendance = models.PositiveIntegerField()
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    full_name = models.CharField(max_length=128)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20)
    additional_notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    venue_name = models.CharField(max_length=128, blank=True, null=True)
    
    class Meta:
        db_table = "inquiries"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["sender", "-created_at"]),
            models.Index(fields=["receiver", "-created_at"]),
            models.Index(fields=["receiver", "status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Inquiry<{self.uid}>"
