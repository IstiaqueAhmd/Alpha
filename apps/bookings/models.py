from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class AvailabilitySlot(TimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        SOFT_HOLD = "soft_hold", "Soft Hold"
        BOOKED = "booked", "Booked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_slots",
        limit_choices_to={"role": "artist"},
    )
    date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "availability_slots"
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_user_date_slot"),
        ]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["date", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.date} {self.status}"


class BookingOffer(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_offers",
    )
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_offers",
        limit_choices_to={"role": "artist"},
        null=True,
        blank=True,
    )
    seatgeek_performer = models.ForeignKey(
        "seatgeek.Performers",
        on_delete=models.SET_NULL,
        related_name="received_offers",
        null=True,
        blank=True,
    )

    title = models.CharField(max_length=255)
    event_date = models.DateField()
    event_time = models.TimeField(null=True, blank=True)
    venue_name = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)

    amount_cents = models.BigIntegerField(default=0)
    budget_min_cents = models.BigIntegerField(null=True, blank=True)
    budget_max_cents = models.BigIntegerField(null=True, blank=True)

    contact_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "booking_offers"
        ordering = ("-event_date",)
        indexes = [
            models.Index(fields=["artist", "status", "-event_date"]),
            models.Index(fields=["requester", "-created_at"]),
            models.Index(fields=["status", "event_date"]),
            models.Index(fields=["seatgeek_performer", "status", "-event_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(artist__isnull=False, seatgeek_performer__isnull=True)
                    | models.Q(artist__isnull=True, seatgeek_performer__isnull=False)
                ),
                name="booking_offer_artist_xor_seatgeek",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class Activity(TimeStampedModel):
    class Verb(models.TextChoices):
        OFFER_RECEIVED = "offer_received", "Offer received"
        OFFER_ACCEPTED = "offer_accepted", "Offer accepted"
        OFFER_REJECTED = "offer_rejected", "Offer rejected"
        AVAILABILITY_UPDATED = "availability_updated", "Availability updated"
        MESSAGE_RECEIVED = "message_received", "Message received"
        PROFILE_UPDATED = "profile_updated", "Profile updated"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    verb = models.CharField(max_length=32, choices=Verb.choices)
    summary = models.CharField(max_length=255)
    detail = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "activities"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.verb} for {self.user_id}"
