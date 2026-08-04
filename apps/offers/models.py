import uuid
from django.conf import settings
from django.db import models
from apps.common.models import TimeStampedModel
from apps.inquiries.models import Inquiry


def generate_uid() -> str:
    return uuid.uuid4().hex[:12]


class Offer(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    uid = models.CharField(max_length=12, default=generate_uid, unique=True, editable=False, db_index=True)

    inquiry = models.OneToOneField(
        Inquiry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offer",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_deal_offers",
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_deal_offers",
    )

    shared_with_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="shared_offers",
        blank=True,
    )
    shared_with_teams = models.ManyToManyField(
        "teams.Team",
        related_name="shared_offers",
        blank=True,
    )

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    artist_name = models.CharField(max_length=128)
    date = models.DateField()
    venue = models.CharField(max_length=128)
    venue_address = models.CharField(max_length=256)
    city_state_country_zip = models.CharField(max_length=128)
    venue_phone = models.CharField(max_length=32)

    offer_amount = models.DecimalField(max_digits=10, decimal_places=2)
    airfare = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    backline = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hotel_ground_transportation = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    catering = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    first_class_sound_and_lighting = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    door_time = models.TimeField()
    expected_attendance = models.IntegerField()
    past_performers = models.CharField(max_length=256, null=True, blank=True)
    social_media_request = models.CharField(max_length=256, null=True, blank=True)
    what_is_event_for = models.CharField(max_length=256, null=True, blank=True)
    other_artists = models.CharField(max_length=256, null=True, blank=True)

    contact_signatory_name = models.CharField(max_length=128)
    contact_signatory_address = models.CharField(max_length=256)
    contact_signatory_contact_info = models.CharField(max_length=32)

    contact_buyer_name = models.CharField(max_length=128)
    contact_buyer_address = models.CharField(max_length=256)
    contact_buyer_contact_info = models.CharField(max_length=32)

    contact_production_name = models.CharField(max_length=128)
    contact_production_contact_info = models.CharField(max_length=32)

    included_facilities = models.JSONField(default=list, blank=True)

    additional_notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "offers"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["sender", "-created_at"]),
            models.Index(fields=["receiver", "-created_at"]),
            models.Index(fields=["receiver", "status", "-created_at"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self) -> str:
        return f"Offer<{self.uid}>"


class OfferSignature(TimeStampedModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="signatures")
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offer_signatures",
    )
    signature = models.ImageField(upload_to="offers/signatures/")
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "offer_signatures"
        ordering = ("signed_at",)
        constraints = [
            models.UniqueConstraint(fields=["offer", "signer"], name="uniq_offer_signer"),
        ]

    def __str__(self) -> str:
        return f"Signature<{self.signer_id}> on {self.offer_id}"


class OfferDocument(TimeStampedModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="documents")
    document = models.FileField(upload_to="offers/documents/")

    class Meta:
        db_table = "offer_documents"

    def __str__(self) -> str:
        return f"Document<{self.pk}> on {self.offer_id}"
