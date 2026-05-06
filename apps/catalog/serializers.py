from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import ArtistProfile, Favorite, Genre, RecentSearch, VenueProfile

UPCOMING_AVAILABLE_LIMIT = 14
UPCOMING_BOOKED_LIMIT = 14
UPCOMING_WINDOW_DAYS = 60


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("id", "name", "slug")


class ArtistProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    genres = GenreSerializer(many=True, read_only=True)
    is_favorited = serializers.SerializerMethodField()
    upcoming_availability = serializers.SerializerMethodField()
    upcoming_booked_dates = serializers.SerializerMethodField()

    class Meta:
        model = ArtistProfile
        fields = (
            "id",
            "user",
            "bio",
            "location",
            "latitude",
            "longitude",
            "cover_image",
            "experience_years",
            "languages",
            "base_price_cents",
            "genres",
            "is_published",
            "is_favorited",
            "upcoming_availability",
            "upcoming_booked_dates",
            "created_at",
        )
        read_only_fields = (
            "id",
            "user",
            "is_favorited",
            "upcoming_availability",
            "upcoming_booked_dates",
            "created_at",
        )

    def get_is_favorited(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Favorite.objects.filter(user=request.user, artist=obj).exists()

    def get_upcoming_availability(self, obj) -> list[dict]:
        """Next free dates within the upcoming window (excluding booked + soft_hold)."""
        from apps.bookings.models import AvailabilitySlot

        slots = self._upcoming_slots(obj)
        blocked = {
            s.date for s in slots
            if s.status in (AvailabilitySlot.Status.BOOKED, AvailabilitySlot.Status.SOFT_HOLD)
        }

        today = timezone.now().date()
        result: list[dict] = []
        cursor = today
        end = today + timedelta(days=UPCOMING_WINDOW_DAYS)
        while cursor <= end and len(result) < UPCOMING_AVAILABLE_LIMIT:
            if cursor not in blocked:
                result.append({
                    "date": cursor.isoformat(),
                    "weekday": cursor.strftime("%a"),
                })
            cursor += timedelta(days=1)
        return result

    def get_upcoming_booked_dates(self, obj) -> list[dict]:
        from apps.bookings.models import AvailabilitySlot

        booked = [s for s in self._upcoming_slots(obj) if s.status == AvailabilitySlot.Status.BOOKED]
        return [
            {
                "date": s.date.isoformat(),
                "weekday": s.date.strftime("%a"),
                "title": s.note,
            }
            for s in booked[:UPCOMING_BOOKED_LIMIT]
        ]

    def _upcoming_slots(self, obj) -> list:
        cached = getattr(obj.user, "upcoming_slots_prefetched", None)
        if cached is not None:
            return cached
        # Fallback for callers that didn't prefetch (kept ordered by date).
        from apps.bookings.models import AvailabilitySlot

        today = timezone.now().date()
        return list(
            AvailabilitySlot.objects.filter(
                user=obj.user,
                date__gte=today,
                date__lte=today + timedelta(days=UPCOMING_WINDOW_DAYS),
            ).order_by("date")
        )


class ArtistProfileUpdateSerializer(serializers.ModelSerializer):
    genre_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Genre.objects.all(),
        write_only=True,
        source="genres",
        required=False,
    )

    class Meta:
        model = ArtistProfile
        fields = (
            "bio",
            "location",
            "latitude",
            "longitude",
            "cover_image",
            "experience_years",
            "languages",
            "base_price_cents",
            "genre_ids",
            "is_published",
        )


class VenueProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = VenueProfile
        fields = (
            "id",
            "user",
            "description",
            "address",
            "location",
            "latitude",
            "longitude",
            "cover_image",
            "capacity",
            "website",
            "is_published",
            "created_at",
        )
        read_only_fields = ("id", "user", "created_at")


class VenueProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VenueProfile
        fields = (
            "description",
            "address",
            "location",
            "latitude",
            "longitude",
            "cover_image",
            "capacity",
            "website",
            "is_published",
        )


class FavoriteCreateSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()


class RecentSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentSearch
        fields = ("id", "query", "location", "radius_miles", "genres", "target_date", "created_at")
        read_only_fields = ("id", "created_at")
