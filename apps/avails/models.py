from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class AvailList(TimeStampedModel):
    """A named collection of artists with their available dates.

    Visibility controls discoverability:
    - public  -- appears in search/browse, anyone can view
    - private -- only the owner and explicitly shared users can see
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="avail_lists",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
    )

    class Meta:
        db_table = "avail_lists"
        indexes = [
            models.Index(fields=["owner", "visibility"]),
            models.Index(fields=["visibility"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.visibility})"


class AvailEntry(TimeStampedModel):
    """One artist slot inside an avail list.

    `artist` points to a platform user. Display overrides (genre, location)
    let the list owner customise how the artist appears in this particular
    list without touching the artist's own profile.
    """

    avail_list = models.ForeignKey(
        AvailList,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="avail_entries",
    )
    genre = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "avail_entries"
        constraints = [
            models.UniqueConstraint(
                fields=["avail_list", "artist"],
                name="uniq_avail_list_artist",
            ),
        ]
        indexes = [
            models.Index(fields=["avail_list", "position"]),
        ]

    def __str__(self) -> str:
        return f"entry {self.artist_id} in list {self.avail_list_id}"


class AvailDate(TimeStampedModel):
    """A single available date for an artist in a list."""

    entry = models.ForeignKey(
        AvailEntry,
        on_delete=models.CASCADE,
        related_name="dates",
    )
    date = models.DateField()

    class Meta:
        db_table = "avail_dates"
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "date"],
                name="uniq_avail_entry_date",
            ),
        ]
        indexes = [
            models.Index(fields=["entry", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.date} for entry {self.entry_id}"


class AvailShare(TimeStampedModel):
    """Explicit share of a list to another user or email address.

    When sharing to a non-platform user, only `shared_email` is set. Once
    they join, the share can be linked to their user record.
    """

    avail_list = models.ForeignKey(
        AvailList,
        on_delete=models.CASCADE,
        related_name="shares",
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="avail_shares_sent",
    )
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="avail_shares_received",
    )
    shared_email = models.EmailField(blank=True)
    message = models.TextField(blank=True)

    class Meta:
        db_table = "avail_shares"
        constraints = [
            models.UniqueConstraint(
                fields=["avail_list", "shared_with"],
                condition=models.Q(shared_with__isnull=False),
                name="uniq_avail_share_user",
            ),
        ]
        indexes = [
            models.Index(fields=["avail_list"]),
            models.Index(fields=["shared_with"]),
        ]

    def __str__(self) -> str:
        target = self.shared_with_id or self.shared_email
        return f"share list {self.avail_list_id} to {target}"
