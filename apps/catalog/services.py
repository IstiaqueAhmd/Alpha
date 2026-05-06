import math
from datetime import date, timedelta

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import User

from .models import ArtistProfile, Favorite, Genre, RecentSearch, VenueProfile

EARTH_RADIUS_MILES = 3958.8
UPCOMING_WINDOW_DAYS = 60


def _prefetch_upcoming_slots():
    """Attach upcoming availability slots to each artist's user under ``upcoming_slots_prefetched``."""
    from apps.bookings.models import AvailabilitySlot

    today = timezone.now().date()
    horizon = today + timedelta(days=UPCOMING_WINDOW_DAYS)
    slots_qs = (
        AvailabilitySlot.objects
        .filter(date__gte=today, date__lte=horizon)
        .order_by("date")
    )
    return Prefetch(
        "user__availability_slots",
        queryset=slots_qs,
        to_attr="upcoming_slots_prefetched",
    )


def _bounding_box(lat: float, lng: float, radius_miles: float) -> tuple[float, float, float, float]:
    """Cheap pre-filter to narrow rows before haversine; still correct after fine filtering."""
    lat_delta = radius_miles / 69.0
    lng_delta = radius_miles / (69.0 * max(math.cos(math.radians(lat)), 1e-6))
    return lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(a))


class CatalogService:
    @staticmethod
    def search_artists(
        *,
        viewer: User | None,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_miles: float | None = None,
        genre_slugs: list[str] | None = None,
        available_on: date | None = None,
        favorites_only: bool = False,
    ) -> QuerySet[ArtistProfile]:
        qs: QuerySet[ArtistProfile] = (
            ArtistProfile.objects
            .select_related("user")
            .prefetch_related("genres", _prefetch_upcoming_slots())
            .filter(is_published=True, user__is_active=True)
        )

        if query:
            qs = qs.filter(Q(user__name__icontains=query) | Q(bio__icontains=query) | Q(location__icontains=query))

        if genre_slugs:
            qs = qs.filter(genres__slug__in=genre_slugs).distinct()

        if favorites_only:
            if not viewer or not viewer.is_authenticated:
                raise PermissionDenied("Sign in to filter by favorites.")
            qs = qs.filter(favorited_by__user=viewer)

        if available_on:
            from apps.bookings.models import AvailabilitySlot
            unavailable_user_ids = AvailabilitySlot.objects.filter(
                date=available_on,
                status__in=[AvailabilitySlot.Status.BOOKED, AvailabilitySlot.Status.SOFT_HOLD],
            ).values_list("user_id", flat=True)
            qs = qs.exclude(user_id__in=list(unavailable_user_ids))

        if latitude is not None and longitude is not None and radius_miles:
            lat_min, lat_max, lng_min, lng_max = _bounding_box(latitude, longitude, radius_miles)
            qs = qs.filter(
                latitude__gte=lat_min, latitude__lte=lat_max,
                longitude__gte=lng_min, longitude__lte=lng_max,
            )
            results = []
            for artist in qs:
                if artist.latitude is None or artist.longitude is None:
                    continue
                if _haversine_miles(latitude, longitude, artist.latitude, artist.longitude) <= radius_miles:
                    results.append(artist.pk)
            qs = (
                ArtistProfile.objects
                .filter(pk__in=results)
                .select_related("user")
                .prefetch_related("genres", _prefetch_upcoming_slots())
            )

        return qs.order_by("-created_at")

    @staticmethod
    def search_venues(
        *,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_miles: float | None = None,
    ) -> QuerySet[VenueProfile]:
        qs: QuerySet[VenueProfile] = (
            VenueProfile.objects
            .select_related("user")
            .filter(is_published=True, user__is_active=True)
        )
        if query:
            qs = qs.filter(
                Q(user__name__icontains=query)
                | Q(description__icontains=query)
                | Q(location__icontains=query)
                | Q(address__icontains=query)
            )
        if latitude is not None and longitude is not None and radius_miles:
            lat_min, lat_max, lng_min, lng_max = _bounding_box(latitude, longitude, radius_miles)
            qs = qs.filter(
                latitude__gte=lat_min, latitude__lte=lat_max,
                longitude__gte=lng_min, longitude__lte=lng_max,
            )
        return qs.order_by("-created_at")

    @staticmethod
    def get_artist_profile(artist_id: int) -> ArtistProfile:
        artist = (
            ArtistProfile.objects
            .select_related("user")
            .prefetch_related("genres", _prefetch_upcoming_slots())
            .filter(pk=artist_id, is_published=True, user__is_active=True)
            .first()
        )
        if not artist:
            raise NotFound("Artist not found.")
        return artist

    @staticmethod
    def get_or_create_own_artist_profile(user: User) -> ArtistProfile:
        if user.role != User.Role.ARTIST:
            raise PermissionDenied("Only artist accounts have an artist profile.")
        profile, _ = ArtistProfile.objects.get_or_create(user=user)
        return profile

    @staticmethod
    def get_or_create_own_venue_profile(user: User) -> VenueProfile:
        if user.role != User.Role.VENUE:
            raise PermissionDenied("Only venue accounts have a venue profile.")
        profile, _ = VenueProfile.objects.get_or_create(user=user)
        return profile


class FavoritesService:
    @staticmethod
    def add(*, user: User, artist_id: int) -> Favorite:
        artist = ArtistProfile.objects.filter(pk=artist_id).first()
        if not artist:
            raise NotFound("Artist not found.")
        favorite, _ = Favorite.objects.get_or_create(user=user, artist=artist)
        return favorite

    @staticmethod
    def remove(*, user: User, artist_id: int) -> None:
        Favorite.objects.filter(user=user, artist_id=artist_id).delete()

    @staticmethod
    def list_for(user: User) -> QuerySet[Favorite]:
        return (
            Favorite.objects
            .select_related("artist__user")
            .prefetch_related("artist__genres")
            .filter(user=user)
            .order_by("-created_at")
        )


class RecentSearchService:
    MAX_HISTORY = 20

    @classmethod
    def record(cls, *, user: User, **fields) -> RecentSearch:
        record = RecentSearch.objects.create(user=user, **fields)
        # trim to last MAX_HISTORY
        ids_to_keep = list(
            RecentSearch.objects.filter(user=user)
            .order_by("-created_at")
            .values_list("id", flat=True)[: cls.MAX_HISTORY]
        )
        RecentSearch.objects.filter(user=user).exclude(id__in=ids_to_keep).delete()
        return record

    @staticmethod
    def list_for(user: User) -> QuerySet[RecentSearch]:
        return RecentSearch.objects.filter(user=user).order_by("-created_at")
