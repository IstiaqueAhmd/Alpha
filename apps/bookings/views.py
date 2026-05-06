from datetime import date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination

from .serializers import (
    ActivitySerializer,
    AvailabilitySlotSerializer,
    AvailabilitySlotUpsertSerializer,
    BookingOfferCreateSerializer,
    BookingOfferSerializer,
)
from .services import (
    ActivityService,
    AvailabilityService,
    BookingService,
    DashboardService,
)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class AvailabilityListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        artist = request.user
        start = _parse_date(request.query_params.get("start"))
        end = _parse_date(request.query_params.get("end"))
        slots = AvailabilityService.list_for_artist(artist, start=start, end=end)
        return Response(
            {"success": True, "results": AvailabilitySlotSerializer(slots, many=True).data},
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        serializer = AvailabilitySlotUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slot = AvailabilityService.upsert(
            request.user,
            slot_date=serializer.validated_data["date"],
            status=serializer.validated_data["status"],
            note=serializer.validated_data.get("note", ""),
        )
        return Response(
            {"success": True, "slot": AvailabilitySlotSerializer(slot).data},
            status=status.HTTP_200_OK,
        )


class AvailabilityDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, slot_date: str):
        parsed = _parse_date(slot_date)
        if not parsed:
            return Response(
                {"success": False, "error": {"code": "invalid", "message": "Invalid date."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        AvailabilityService.delete(request.user, parsed)
        return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)


class PublicArtistAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, artist_id: int):
        from apps.accounts.models import User
        artist = User.objects.filter(pk=artist_id, role=User.Role.ARTIST, is_active=True).first()
        if not artist:
            return Response(
                {"success": False, "error": {"code": "not_found", "message": "Artist not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        start = _parse_date(request.query_params.get("start"))
        end = _parse_date(request.query_params.get("end"))
        slots = AvailabilityService.list_for_artist(artist, start=start, end=end)
        return Response(
            {"success": True, "results": AvailabilitySlotSerializer(slots, many=True).data},
            status=status.HTTP_200_OK,
        )


class BookingOfferListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request):
        scope = request.query_params.get("scope", "received")
        if scope == "sent":
            qs = BookingService.list_for_requester(request.user)
        else:
            status_filter = request.query_params.get("status")
            qs = BookingService.list_for_artist(request.user, status_filter=status_filter)
        qs = qs.order_by("-created_at")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(BookingOfferSerializer(page, many=True).data)

    def post(self, request):
        serializer = BookingOfferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        artist_id = data.pop("artist_id")
        offer = BookingService.create_offer(requester=request.user, artist_id=artist_id, **data)
        return Response(
            {"success": True, "offer": BookingOfferSerializer(offer).data, "message": "Booking request sent."},
            status=status.HTTP_201_CREATED,
        )


class BookingOfferAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, offer_id: int):
        offer = BookingService.accept(artist=request.user, offer_id=offer_id)
        return Response(
            {"success": True, "offer": BookingOfferSerializer(offer).data},
            status=status.HTTP_200_OK,
        )


class BookingOfferRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, offer_id: int):
        offer = BookingService.reject(artist=request.user, offer_id=offer_id)
        return Response(
            {"success": True, "offer": BookingOfferSerializer(offer).data},
            status=status.HTTP_200_OK,
        )


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        kpis = DashboardService.kpis_for_artist(request.user)
        return Response(
            {
                "success": True,
                "active_offers": kpis["active_offers"],
                "confirmed_bookings": kpis["confirmed_bookings"],
                "total_earnings_cents": kpis["total_earnings_cents"],
                "growth_percent": kpis["growth_percent"],
                "incoming_offers": BookingOfferSerializer(kpis["incoming_offers"], many=True).data,
                "upcoming_bookings": BookingOfferSerializer(kpis["upcoming_bookings"], many=True).data,
                "recent_activities": ActivitySerializer(kpis["recent_activities"], many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ActivityFeedView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request):
        qs = ActivityService.list_for(request.user)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(ActivitySerializer(page, many=True).data)
