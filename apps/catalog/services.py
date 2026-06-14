import math
from datetime import date, timedelta

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import User

from .models import ArtistProfile, Favorite, Genre, RecentSearch, VenueProfile

EARTH_RADIUS_MILES = 3958.8
AVAILABILITY_WINDOW_DAYS = 365


def _prefetch_upcoming_slots():
    """Attach 1-year availability slots to each artist's user under ``upcoming_slots_prefetched``."""
    from apps.bookings.models import AvailabilitySlot

    today = timezone.now().date()
    horizon = today + timedelta(days=AVAILABILITY_WINDOW_DAYS)
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


def _resolve_availability_range(
    available_on: date | None,
    available_from: date | None,
    available_to: date | None,
) -> tuple[date | None, date | None]:
    """`available_on` is a single-day shortcut; explicit from/to override either end."""
    start = available_from or available_on
    end = available_to or available_on
    if start and not end:
        end = start
    if end and not start:
        start = end
    if start and end and start > end:
        start, end = end, start
    return start, end


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
        available_from: date | None = None,
        available_to: date | None = None,
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

        block_from, block_to = _resolve_availability_range(available_on, available_from, available_to)
        if block_from and block_to:
            from apps.bookings.models import AvailabilitySlot

            unavailable_user_ids = AvailabilitySlot.objects.filter(
                date__gte=block_from,
                date__lte=block_to,
                status__in=[AvailabilitySlot.Status.BOOKED, AvailabilitySlot.Status.SOFT_HOLD],
            ).values_list("user_id", flat=True)
            qs = qs.exclude(user_id__in=list(unavailable_user_ids))

        if latitude is not None and longitude is not None and radius_miles:
            # Internal artists have no event-venue geo-data; filter them
            # the same way SeatGeek performers are filtered — by checking
            # whether they have *any* confirmed/pending booking at a venue
            # within the search radius.  BookingOffer stores only a text
            # address (no lat/lng), so we cannot geo-filter internal
            # artists and must exclude them when a location filter is
            # active.  They may still appear via SeatGeek performer results.
            qs = qs.none()

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
            .prefetch_related(_prefetch_upcoming_slots())
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
    def add(*, user: User, artist_id: str) -> Favorite:
        artist, sg_performer = FavoritesService._resolve_target(artist_id)
        if not artist and not sg_performer:
            raise NotFound("Artist not found.")
        favorite, _ = Favorite.objects.get_or_create(
            user=user, artist=artist, seatgeek_performer=sg_performer,
        )
        return favorite

    @staticmethod
    def remove(*, user: User, artist_id: str) -> None:
        raw = str(artist_id)
        if raw.isdigit():
            removed, _ = Favorite.objects.filter(
                user=user, artist_id=int(raw), seatgeek_performer__isnull=True,
            ).delete()
            if removed:
                return
        Favorite.objects.filter(
            user=user, seatgeek_performer_id=raw, artist__isnull=True,
        ).delete()

    @staticmethod
    def list_for(user: User) -> QuerySet[Favorite]:
        return (
            Favorite.objects
            .select_related("artist__user", "seatgeek_performer")
            .prefetch_related("artist__genres", "seatgeek_performer__performergenres_set")
            .filter(user=user)
            .order_by("-created_at")
        )

    @staticmethod
    def _resolve_target(artist_id: str):
        from apps.seatgeek.models import Performers as SeatGeekPerformer

        raw = str(artist_id)
        if raw.isdigit():
            artist = ArtistProfile.objects.filter(pk=int(raw)).first()
            if artist:
                return artist, None
        sg = SeatGeekPerformer.objects.filter(pk=raw).first()
        return None, sg


class SeatGeekService:
    @staticmethod
    def search_performers(
        *,
        query: str | None = None,
        available_on: date | None = None,
        available_from: date | None = None,
        available_to: date | None = None,
        genre_slugs: list[str] | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_miles: float | None = None,
    ) -> QuerySet:
        from apps.seatgeek.models import PerformerEvents, PerformerGenres, Performers, PerformerSeatgeekGenres

        qs = Performers.objects.prefetch_related("performergenres_set", "performerseatgeekgenres_set__seatgeek_genre").all()
        if query:
            qs = qs.filter(name__icontains=query)

        if genre_slugs:
            genre_q = Q()
            sg_genre_q = Q()
            for slug in genre_slugs:
                genre_q |= Q(genre__iexact=slug) | Q(genre__icontains=slug)
                sg_genre_q |= Q(seatgeek_genre__slug__iexact=slug) | Q(seatgeek_genre__slug__icontains=slug)
            
            genre_performer_ids = set(
                PerformerGenres.objects
                .filter(genre_q)
                .values_list("performer_id", flat=True)
            )
            sg_genre_performer_ids = set(
                PerformerSeatgeekGenres.objects
                .filter(sg_genre_q)
                .values_list("performer_id", flat=True)
            )
            
            qs = qs.filter(pk__in=list(genre_performer_ids | sg_genre_performer_ids))

        block_from, block_to = _resolve_availability_range(available_on, available_from, available_to)

        # When a date range is given, keep only performers who actually have
        # events within that window — performers with no matching events are
        # excluded from results.
        if block_from and block_to:
            performers_with_events = (
                PerformerEvents.objects
                .filter(event__start_date__lte=block_to, event__end_date__gte=block_from)
                .values_list("performer_id", flat=True)
                .distinct()
            )
            qs = qs.filter(pk__in=list(performers_with_events))

        # Performers have no own location — derive geographic footprint from their events' venue
        # coordinates. A performer is "near" the search point if ANY of their events' venues falls
        # within the bounding box (cheap pre-filter) and inside the great-circle radius (haversine).
        # When a date range is also active, only events within that window are considered.
        if latitude is not None and longitude is not None and radius_miles:
            lat_min, lat_max, lng_min, lng_max = _bounding_box(latitude, longitude, radius_miles)
            event_filters = Q(
                event__venue__lat__gte=lat_min, event__venue__lat__lte=lat_max,
                event__venue__long__gte=lng_min, event__venue__long__lte=lng_max,
            )
            if block_from and block_to:
                event_filters &= Q(
                    event__start_date__lte=block_to,
                    event__end_date__gte=block_from,
                )
            candidates = (
                PerformerEvents.objects
                .filter(event_filters)
                .values_list("performer_id", "event__venue__lat", "event__venue__long")
            )
            near_performer_ids: set[str] = set()
            for performer_id, venue_lat, venue_lng in candidates:
                if performer_id in near_performer_ids:
                    continue  # already matched on an earlier venue, skip the haversine
                if venue_lat is None or venue_lng is None:
                    continue
                if _haversine_miles(latitude, longitude, venue_lat, venue_lng) <= radius_miles:
                    near_performer_ids.add(performer_id)
            qs = qs.filter(pk__in=near_performer_ids)

        return qs.order_by("name")

    @staticmethod
    def get_booked_ranges_map(
        performer_ids: list[str],
        *,
        from_date: date,
        to_date: date,
    ) -> dict[str, list[dict]]:
        """performer_id → list of event ranges overlapping [from_date, to_date], clipped to that window."""
        from apps.seatgeek.models import PerformerEvents

        if not performer_ids:
            return {}

        rows = (
            PerformerEvents.objects
            .select_related("event", "event__venue")
            .filter(
                performer_id__in=performer_ids,
                event__start_date__lte=to_date,
                event__end_date__gte=from_date,
            )
            .order_by("event__start_date")
        )

        out: dict[str, list[dict]] = {}
        for pe in rows:
            ev = pe.event
            clipped_start = ev.start_date if ev.start_date > from_date else from_date
            clipped_end = ev.end_date if ev.end_date < to_date else to_date
            out.setdefault(pe.performer_id, []).append({
                "event_id": ev.id,
                "event_name": ev.name,
                "start_date": clipped_start.isoformat(),
                "end_date": clipped_end.isoformat(),
                "weekday": clipped_start.strftime("%a"),
                "venue": ev.venue.name if ev.venue_id and ev.venue else (ev.location_name or ""),
                "city": ev.venue.city if ev.venue_id and ev.venue else "",
            })
        return out

    @staticmethod
    def get_venue_booked_ranges_map(
        venue_ids: list[str],
        *,
        from_date: date,
        to_date: date,
    ) -> dict[str, list[dict]]:
        """venue_id → list of event ranges overlapping [from_date, to_date], clipped to that window."""
        from apps.seatgeek.models import Events

        if not venue_ids:
            return {}

        rows = (
            Events.objects
            .select_related("venue")
            .filter(
                venue_id__in=venue_ids,
                start_date__lte=to_date,
                end_date__gte=from_date,
            )
            .order_by("start_date")
        )

        out: dict[str, list[dict]] = {}
        for ev in rows:
            clipped_start = ev.start_date if ev.start_date > from_date else from_date
            clipped_end = ev.end_date if ev.end_date < to_date else to_date
            out.setdefault(ev.venue_id, []).append({
                "event_id": ev.id,
                "event_name": ev.name,
                "start_date": clipped_start.isoformat(),
                "end_date": clipped_end.isoformat(),
                "weekday": clipped_start.strftime("%a"),
                "venue": ev.venue.name if ev.venue_id and ev.venue else (ev.location_name or ""),
                "city": ev.venue.city if ev.venue_id and ev.venue else "",
            })
        return out

    @staticmethod
    def search_venues(
        *,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_miles: float | None = None,
    ) -> QuerySet:
        from apps.seatgeek.models import Venues
        qs = Venues.objects.all()
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(city__icontains=query) | Q(address__icontains=query))
        if latitude is not None and longitude is not None and radius_miles:
            lat_min, lat_max, lng_min, lng_max = _bounding_box(latitude, longitude, radius_miles)
            qs = qs.filter(
                lat__gte=lat_min, lat__lte=lat_max,
                long__gte=lng_min, long__lte=lng_max,
            )
        return qs.order_by("name")


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
