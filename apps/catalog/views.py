from datetime import date

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination

from .models import ArtistProfile, Genre, VenueProfile
from .serializers import (
    ArtistProfileSerializer,
    ArtistProfileUpdateSerializer,
    FavoriteCreateSerializer,
    GenreSerializer,
    RecentSearchSerializer,
    SeatGeekPerformerSerializer,
    SeatGeekVenueSerializer,
    VenueProfileSerializer,
    VenueProfileUpdateSerializer,
)
from .services import CatalogService, FavoritesService, RecentSearchService, SeatGeekService


def _parse_float(raw: str | None) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse_date(raw: str | None) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_bool(raw: str | None) -> bool:
    return str(raw).lower() in {"1", "true", "yes"}


class GenreListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {"success": True, "results": GenreSerializer(Genre.objects.all(), many=True).data},
            status=status.HTTP_200_OK,
        )


class ArtistListView(APIView):
    permission_classes = [AllowAny]
    pagination_class = StandardPagination

    def get(self, request):
        params = request.query_params
        query = params.get("q") or None
        latitude = _parse_float(params.get("latitude"))
        longitude = _parse_float(params.get("longitude"))
        radius = _parse_float(params.get("radius_miles"))
        available_on = _parse_date(params.get("available_on"))
        favorites_only = _parse_bool(params.get("favorites_only"))
        genre_slugs = [s for s in params.get("genres", "").split(",") if s.strip()]

        internal_qs = CatalogService.search_artists(
            viewer=request.user if request.user.is_authenticated else None,
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius,
            genre_slugs=genre_slugs or None,
            available_on=available_on,
            favorites_only=favorites_only,
        )

        if request.user.is_authenticated and (query or genre_slugs or available_on or radius):
            RecentSearchService.record(
                user=request.user,
                query=query or "",
                location=params.get("location", "") or "",
                radius_miles=int(radius) if radius else None,
                genres=genre_slugs,
                target_date=available_on,
            )

        sg_qs = SeatGeekService.search_performers(query=query)

        paginator = self.pagination_class()
        limit  = paginator.get_limit(request)  or paginator.default_limit
        offset = paginator.get_offset(request)

        internal_count = internal_qs.count()
        sg_count       = sg_qs.count()
        total          = internal_count + sg_count

        # Slice only the rows needed for this page from each source.
        int_start  = min(offset, internal_count)
        int_end    = min(offset + limit, internal_count)
        int_page   = list(internal_qs[int_start:int_end])
        remaining  = limit - len(int_page)
        sg_start   = max(0, offset - internal_count)
        sg_page    = list(sg_qs[sg_start: sg_start + remaining]) if remaining > 0 else []

        int_data = [
            {"source": "internal", **ArtistProfileSerializer(a, context={"request": request}).data}
            for a in int_page
        ]
        sg_data = [
            {"source": "seatgeek", **SeatGeekPerformerSerializer(p).data}
            for p in sg_page
        ]

        paginator.count  = total
        paginator.limit  = limit
        paginator.offset = offset
        paginator.request = request
        return paginator.get_paginated_response(int_data + sg_data)


class ArtistDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, artist_id: str):
        # Integer ID → internal ArtistProfile
        try:
            pk = int(artist_id)
            artist = CatalogService.get_artist_profile(pk)
            return Response(
                {"success": True, "source": "internal",
                 "artist": ArtistProfileSerializer(artist, context={"request": request}).data},
                status=status.HTTP_200_OK,
            )
        except (ValueError, TypeError):
            pass

        # String ID → SeatGeek Performer
        from apps.seatgeek.models import Performers
        performer = Performers.objects.prefetch_related("performergenres_set").filter(pk=artist_id).first()
        if not performer:
            return Response(
                {"success": False, "error": {"code": "not_found", "message": "Artist not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {"success": True, "source": "seatgeek",
             "artist": SeatGeekPerformerSerializer(performer).data},
            status=status.HTTP_200_OK,
        )


class MyArtistProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = CatalogService.get_or_create_own_artist_profile(request.user)
        return Response(
            {"success": True, "artist": ArtistProfileSerializer(profile, context={"request": request}).data},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        profile = CatalogService.get_or_create_own_artist_profile(request.user)
        serializer = ArtistProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"success": True, "artist": ArtistProfileSerializer(profile, context={"request": request}).data},
            status=status.HTTP_200_OK,
        )


class VenueListView(APIView):
    permission_classes = [AllowAny]
    pagination_class = StandardPagination

    def get(self, request):
        params = request.query_params
        query = params.get("q") or None
        latitude = _parse_float(params.get("latitude"))
        longitude = _parse_float(params.get("longitude"))
        radius_miles = _parse_float(params.get("radius_miles"))

        internal_qs = CatalogService.search_venues(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius_miles,
        )
        sg_qs = SeatGeekService.search_venues(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius_miles,
        )

        paginator = self.pagination_class()
        limit  = paginator.get_limit(request) or paginator.default_limit
        offset = paginator.get_offset(request)

        internal_count = internal_qs.count()
        sg_count       = sg_qs.count()
        total          = internal_count + sg_count

        int_start = min(offset, internal_count)
        int_end   = min(offset + limit, internal_count)
        int_page  = list(internal_qs[int_start:int_end])
        remaining = limit - len(int_page)
        sg_start  = max(0, offset - internal_count)
        sg_page   = list(sg_qs[sg_start: sg_start + remaining]) if remaining > 0 else []

        int_data = [{"source": "internal", **VenueProfileSerializer(v).data}  for v in int_page]
        sg_data  = [{"source": "seatgeek", **SeatGeekVenueSerializer(v).data} for v in sg_page]

        paginator.count   = total
        paginator.limit   = limit
        paginator.offset  = offset
        paginator.request = request
        return paginator.get_paginated_response(int_data + sg_data)


class VenueDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, venue_id: str):
        # Integer ID → internal VenueProfile
        try:
            pk = int(venue_id)
            venue = VenueProfile.objects.select_related("user").filter(pk=pk, is_published=True).first()
            if not venue:
                return Response(
                    {"success": False, "error": {"code": "not_found", "message": "Venue not found."}},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response({"success": True, "source": "internal", "venue": VenueProfileSerializer(venue).data})
        except (ValueError, TypeError):
            pass

        # String ID → SeatGeek Venue
        from apps.seatgeek.models import Venues
        sg_venue = Venues.objects.filter(pk=venue_id).first()
        if not sg_venue:
            return Response(
                {"success": False, "error": {"code": "not_found", "message": "Venue not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "source": "seatgeek", "venue": SeatGeekVenueSerializer(sg_venue).data})


class MyVenueProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = CatalogService.get_or_create_own_venue_profile(request.user)
        return Response({"success": True, "venue": VenueProfileSerializer(profile).data})

    def patch(self, request):
        profile = CatalogService.get_or_create_own_venue_profile(request.user)
        serializer = VenueProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "venue": VenueProfileSerializer(profile).data})


class FavoritesView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request):
        favorites = FavoritesService.list_for(request.user)
        artists = [fav.artist for fav in favorites]
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(artists, request, view=self)
        serializer = ArtistProfileSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = FavoriteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        FavoritesService.add(user=request.user, artist_id=serializer.validated_data["artist_id"])
        return Response({"success": True}, status=status.HTTP_201_CREATED)


class FavoriteDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, artist_id: int):
        FavoritesService.remove(user=request.user, artist_id=artist_id)
        return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)


class RecentSearchesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        searches = RecentSearchService.list_for(request.user)[:20]
        return Response(
            {"success": True, "results": RecentSearchSerializer(searches, many=True).data},
            status=status.HTTP_200_OK,
        )
