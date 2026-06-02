from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    class Role(models.TextChoices):
        ARTIST = "artist", "Artist"
        AGENT = "agent", "Agent"
        TALENT_BUYER = "talent-buyer", "Talent Buyer"
        VENUE = "venue", "Venue"
        ORGANIZER = "organizer", "Organizer"

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=32, choices=Role.choices)
    image = models.ImageField(upload_to="avatars/", blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True)
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)

    email_verified_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name", "role"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def mark_email_verified(self) -> None:
        if self.email_verified_at is None:
            self.email_verified_at = timezone.now()
            self.save(update_fields=["email_verified_at", "updated_at"])


class EmailOTP(TimeStampedModel):
    class Purpose(models.TextChoices):
        EMAIL_VERIFICATION = "email_verification", "Email Verification"
        PASSWORD_RESET = "password_reset", "Password Reset"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_otps",
    )
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    otp_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "email_otps"
        indexes = [
            models.Index(fields=["user", "purpose", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.purpose} for {self.user_id}"

    def is_valid(self, max_attempts: int) -> bool:
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.attempts < max_attempts
        )


class NotificationPreferences(TimeStampedModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    new_booking_requests = models.BooleanField(default=True)
    offer_responses = models.BooleanField(default=True)
    email_delivery_updates = models.BooleanField(default=False)

    class Meta:
        db_table = "notification_preferences"

    def __str__(self) -> str:
        return f"prefs for {self.user_id}"
