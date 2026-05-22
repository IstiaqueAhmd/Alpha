from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.common.models import TimeStampedModel


class Genre(TimeStampedModel):
    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=80, unique=True)

    class Meta:
        db_table = "genres"
        ordering = ("name",)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class ArtistProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="artist_profile",
        limit_choices_to={"role": "artist"},
    )
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    cover_image = models.ImageField(upload_to="artists/covers/", blank=True, null=True)

    experience_years = models.PositiveSmallIntegerField(default=0)
    languages = models.JSONField(default=list, blank=True)
    base_price_cents = models.BigIntegerField(default=0)

    genres = models.ManyToManyField(Genre, related_name="artists", blank=True)

    is_published = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "artist_profiles"
        indexes = [
            models.Index(fields=["is_published"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self) -> str:
        return f"ArtistProfile<{self.user_id}>"


class VenueProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="venue_profile",
        limit_choices_to={"role": "venue"},
    )
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    cover_image = models.ImageField(upload_to="venues/covers/", blank=True, null=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    website = models.URLField(blank=True)

    is_published = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "venue_profiles"

    def __str__(self) -> str:
        return f"VenueProfile<{self.user_id}>"


class Favorite(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    artist = models.ForeignKey(
        ArtistProfile,
        on_delete=models.CASCADE,
        related_name="favorited_by",
        null=True,
        blank=True,
    )
    seatgeek_performer = models.ForeignKey(
        "seatgeek.Performers",
        on_delete=models.CASCADE,
        related_name="favorited_by",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "favorites"
        constraints = [
            models.UniqueConstraint(fields=["user", "artist"], name="unique_user_artist_favorite"),
            models.UniqueConstraint(
                fields=["user", "seatgeek_performer"], name="unique_user_sg_performer_favorite"
            ),
            models.CheckConstraint(
                check=(
                    models.Q(artist__isnull=False, seatgeek_performer__isnull=True)
                    | models.Q(artist__isnull=True, seatgeek_performer__isnull=False)
                ),
                name="favorite_artist_xor_seatgeek",
            ),
        ]
        indexes = [models.Index(fields=["user", "-created_at"])]


class RecentSearch(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recent_searches",
    )
    query = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    radius_miles = models.PositiveIntegerField(null=True, blank=True)
    genres = models.JSONField(default=list, blank=True)
    target_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "recent_searches"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]
