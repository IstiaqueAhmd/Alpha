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
    VenueProfileSerializer,
    VenueProfileUpdateSerializer,
)
from .services import CatalogService, FavoritesService, RecentSearchService


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
        latitude = _parse_float(params.get("latitude"))
        longitude = _parse_float(params.get("longitude"))
        radius = _parse_float(params.get("radius_miles"))
        available_on = _parse_date(params.get("available_on"))
        favorites_only = _parse_bool(params.get("favorites_only"))
        genre_slugs = [s for s in params.get("genres", "").split(",") if s.strip()]

        qs = CatalogService.search_artists(
            viewer=request.user if request.user.is_authenticated else None,
            query=params.get("q") or None,
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius,
            genre_slugs=genre_slugs or None,
            available_on=available_on,
            favorites_only=favorites_only,
        )

        if request.user.is_authenticated and (params.get("q") or genre_slugs or available_on or radius):
            RecentSearchService.record(
                user=request.user,
                query=params.get("q", "") or "",
                location=params.get("location", "") or "",
                radius_miles=int(radius) if radius else None,
                genres=genre_slugs,
                target_date=available_on,
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ArtistProfileSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class ArtistDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, artist_id: int):
        artist = CatalogService.get_artist_profile(artist_id)
        return Response(
            {"success": True, "artist": ArtistProfileSerializer(artist, context={"request": request}).data},
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
        qs = CatalogService.search_venues(
            query=params.get("q") or None,
            latitude=_parse_float(params.get("latitude")),
            longitude=_parse_float(params.get("longitude")),
            radius_miles=_parse_float(params.get("radius_miles")),
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = VenueProfileSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class VenueDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, venue_id: int):
        venue = VenueProfile.objects.select_related("user").filter(pk=venue_id, is_published=True).first()
        if not venue:
            return Response(
                {"success": False, "error": {"code": "not_found", "message": "Venue not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "venue": VenueProfileSerializer(venue).data})


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
