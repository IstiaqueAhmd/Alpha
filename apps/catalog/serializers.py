from datetime import date as date_cls
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.seatgeek.models import Performers as SeatGeekPerformer
from apps.seatgeek.models import Venues as SeatGeekVenue

from .models import ArtistProfile, Favorite, Genre, RecentSearch, VenueProfile

AVAILABILITY_WINDOW_DAYS = 365


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("id", "name", "slug")


class ArtistProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    genres = GenreSerializer(many=True, read_only=True)
    is_favorited = serializers.SerializerMethodField()
    booked_dates = serializers.SerializerMethodField()
    available_ranges = serializers.SerializerMethodField()

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
            "booked_dates",
            "available_ranges",
            "created_at",
        )
        read_only_fields = (
            "id",
            "user",
            "is_favorited",
            "booked_dates",
            "available_ranges",
            "created_at",
        )

    def get_is_favorited(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Favorite.objects.filter(user=request.user, artist=obj).exists()

    def get_booked_dates(self, obj) -> list[dict]:
        from apps.bookings.models import AvailabilitySlot

        return [
            {
                "start_date": s.date.isoformat(),
                "end_date": s.date.isoformat(),
                "weekday": s.date.strftime("%a"),
                "title": s.note or "",
            }
            for s in self._upcoming_slots(obj)
            if s.status == AvailabilitySlot.Status.BOOKED
        ]

    def get_available_ranges(self, obj) -> list[dict]:
        from apps.bookings.models import AvailabilitySlot

        today = timezone.now().date()
        horizon = today + timedelta(days=AVAILABILITY_WINDOW_DAYS)
        blocked = sorted({
            s.date for s in self._upcoming_slots(obj)
            if s.status in (AvailabilitySlot.Status.BOOKED, AvailabilitySlot.Status.SOFT_HOLD)
        })

        merged: list[list] = []
        for d in blocked:
            if merged and d <= merged[-1][1] + timedelta(days=1):
                merged[-1][1] = d
            else:
                merged.append([d, d])

        free: list[dict] = []
        cursor = today
        for s, e in merged:
            if cursor < s:
                free.append({"start": cursor.isoformat(), "end": (s - timedelta(days=1)).isoformat()})
            if e >= cursor:
                cursor = e + timedelta(days=1)
        if cursor <= horizon:
            free.append({"start": cursor.isoformat(), "end": horizon.isoformat()})
        return free

    def _upcoming_slots(self, obj) -> list:
        cached = getattr(obj.user, "upcoming_slots_prefetched", None)
        if cached is not None:
            return cached
        from apps.bookings.models import AvailabilitySlot

        today = timezone.now().date()
        return list(
            AvailabilitySlot.objects.filter(
                user=obj.user,
                date__gte=today,
                date__lte=today + timedelta(days=AVAILABILITY_WINDOW_DAYS),
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
    booked_dates = serializers.SerializerMethodField()
    available_ranges = serializers.SerializerMethodField()

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
            "booked_dates",
            "available_ranges",
            "created_at",
        )
        read_only_fields = ("id", "user", "booked_dates", "available_ranges", "created_at")

    def get_booked_dates(self, obj) -> list[dict]:
        from apps.bookings.models import AvailabilitySlot

        return [
            {
                "start_date": s.date.isoformat(),
                "end_date": s.date.isoformat(),
                "weekday": s.date.strftime("%a"),
                "title": s.note or "",
            }
            for s in self._upcoming_slots(obj)
            if s.status == AvailabilitySlot.Status.BOOKED
        ]

    def get_available_ranges(self, obj) -> list[dict]:
        from apps.bookings.models import AvailabilitySlot

        today = timezone.now().date()
        horizon = today + timedelta(days=AVAILABILITY_WINDOW_DAYS)
        blocked = sorted({
            s.date for s in self._upcoming_slots(obj)
            if s.status in (AvailabilitySlot.Status.BOOKED, AvailabilitySlot.Status.SOFT_HOLD)
        })

        merged: list[list] = []
        for d in blocked:
            if merged and d <= merged[-1][1] + timedelta(days=1):
                merged[-1][1] = d
            else:
                merged.append([d, d])

        free: list[dict] = []
        cursor = today
        for s, e in merged:
            if cursor < s:
                free.append({"start": cursor.isoformat(), "end": (s - timedelta(days=1)).isoformat()})
            if e >= cursor:
                cursor = e + timedelta(days=1)
        if cursor <= horizon:
            free.append({"start": cursor.isoformat(), "end": horizon.isoformat()})
        return free

    def _upcoming_slots(self, obj) -> list:
        cached = getattr(obj.user, "upcoming_slots_prefetched", None)
        if cached is not None:
            return cached
        from apps.bookings.models import AvailabilitySlot

        today = timezone.now().date()
        return list(
            AvailabilitySlot.objects.filter(
                user=obj.user,
                date__gte=today,
                date__lte=today + timedelta(days=AVAILABILITY_WINDOW_DAYS),
            ).order_by("date")
        )


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
    artist_id = serializers.CharField(max_length=191)


class RecentSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentSearch
        fields = ("id", "query", "location", "radius_miles", "genres", "target_date", "created_at")
        read_only_fields = ("id", "created_at")


class SeatGeekPerformerSerializer(serializers.ModelSerializer):
    source = serializers.CharField(default="seatgeek", read_only=True)
    genres = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    booked_dates = serializers.SerializerMethodField()
    available_ranges = serializers.SerializerMethodField()

    class Meta:
        model = SeatGeekPerformer
        fields = (
            "id",
            "source",
            "name",
            "image",
            "url",
            "score",
            "genres",
            "is_favorited",
            "provider_id",
            "provider_name",
            "booked_dates",
            "available_ranges",
            "created_at",
        )

    def get_is_favorited(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Favorite.objects.filter(user=request.user, seatgeek_performer=obj).exists()

    def get_genres(self, obj) -> list[str]:
        genres = set()
        
        # Free-text genres
        cached_free = getattr(obj, "_prefetched_objects_cache", {}).get("performergenres_set")
        if cached_free is not None:
            for pg in cached_free:
                genres.add(pg.genre)
        else:
            for genre in obj.performergenres_set.values_list("genre", flat=True):
                genres.add(genre)
                
        # Structured seatgeek genres
        cached_sg = getattr(obj, "_prefetched_objects_cache", {}).get("performerseatgeekgenres_set")
        if cached_sg is not None:
            for psg in cached_sg:
                genres.add(psg.seatgeek_genre.name)
        else:
            for name in obj.performerseatgeekgenres_set.values_list("seatgeek_genre__name", flat=True):
                genres.add(name)
                
        return sorted(list(genres))

    def get_booked_dates(self, obj) -> list[dict]:
        return self._booked_ranges(obj)

    def get_available_ranges(self, obj) -> list[dict]:
        today = timezone.now().date()
        horizon = today + timedelta(days=AVAILABILITY_WINDOW_DAYS)
        booked = self._booked_ranges(obj)

        intervals = sorted(
            (date_cls.fromisoformat(b["start_date"]), date_cls.fromisoformat(b["end_date"]))
            for b in booked
        )
        merged: list[list] = []
        for s, e in intervals:
            if merged and s <= merged[-1][1] + timedelta(days=1):
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])

        free: list[dict] = []
        cursor = today
        for s, e in merged:
            if cursor < s:
                free.append({"start": cursor.isoformat(), "end": (s - timedelta(days=1)).isoformat()})
            if e >= cursor:
                cursor = e + timedelta(days=1)
        if cursor <= horizon:
            free.append({"start": cursor.isoformat(), "end": horizon.isoformat()})
        return free

    def _booked_ranges(self, obj) -> list[dict]:
        ranges_map = self.context.get("sg_booked_ranges_map") or {}
        if obj.id in ranges_map:
            return ranges_map[obj.id]
        from apps.catalog.services import SeatGeekService

        today = timezone.now().date()
        horizon = today + timedelta(days=AVAILABILITY_WINDOW_DAYS)
        return SeatGeekService.get_booked_ranges_map(
            [obj.id], from_date=today, to_date=horizon,
        ).get(obj.id, [])


class SeatGeekVenueSerializer(serializers.ModelSerializer):
    source = serializers.CharField(default="seatgeek", read_only=True)
    latitude = serializers.FloatField(source="lat")
    longitude = serializers.FloatField(source="long")
    website = serializers.CharField(source="provider_url")
    booked_dates = serializers.SerializerMethodField()
    available_ranges = serializers.SerializerMethodField()

    class Meta:
        model = SeatGeekVenue
        fields = (
            "id",
            "source",
            "name",
            "address",
            "city",
            "state",
            "postal_code",
            "country",
            "latitude",
            "longitude",
            "capacity",
            "score",
            "website",
            "provider_id",
            "provider_name",
            "booked_dates",
            "available_ranges",
            "created_at",
        )

    def get_booked_dates(self, obj) -> list[dict]:
        return self._booked_ranges(obj)

    def get_available_ranges(self, obj) -> list[dict]:
        today = timezone.now().date()
        horizon = today + timedelta(days=AVAILABILITY_WINDOW_DAYS)
        booked = self._booked_ranges(obj)

        intervals = sorted(
            (date_cls.fromisoformat(b["start_date"]), date_cls.fromisoformat(b["end_date"]))
            for b in booked
        )
        merged: list[list] = []
        for s, e in intervals:
            if merged and s <= merged[-1][1] + timedelta(days=1):
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])

        free: list[dict] = []
        cursor = today
        for s, e in merged:
            if cursor < s:
                free.append({"start": cursor.isoformat(), "end": (s - timedelta(days=1)).isoformat()})
            if e >= cursor:
                cursor = e + timedelta(days=1)
        if cursor <= horizon:
            free.append({"start": cursor.isoformat(), "end": horizon.isoformat()})
        return free

    def _booked_ranges(self, obj) -> list[dict]:
        ranges_map = self.context.get("sg_venue_booked_ranges_map") or {}
        if obj.id in ranges_map:
            return ranges_map[obj.id]
        from apps.catalog.services import SeatGeekService

        today = timezone.now().date()
        horizon = today + timedelta(days=AVAILABILITY_WINDOW_DAYS)
        return SeatGeekService.get_venue_booked_ranges_map(
            [obj.id], from_date=today, to_date=horizon,
        ).get(obj.id, [])
