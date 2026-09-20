from datetime import date

from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, extend_schema

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
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


class InvalidStatusFilter(ValidationError):
    default_code = "invalid_status_filter"
    default_detail = "Invalid status. Choose one of: pending, confirmed, past."


class BookingOfferListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    ALLOWED_STATUS = {"pending", "accepted", "rejected"}

    @extend_schema(
        summary="List booking offers",
        description="Retrieve a paginated list of booking offers (sent or received).",
        parameters=[
            OpenApiParameter(name="scope", type=str, description="Scope of offers (received/sent). Default: received", required=False),
            OpenApiParameter(name="status", type=str, description="Filter offers by status (pending/accepted/rejected)", required=False)
        ],
        responses={200: BookingOfferSerializer(many=True)}
    )
    def get(self, request):
        scope = request.query_params.get("scope", "received")
        status_filter = request.query_params.get("status")

        if status_filter and status_filter not in self.ALLOWED_STATUS:
            raise ValidationError({"status": "Invalid status. Must be one of: " + ", ".join(self.ALLOWED_STATUS)})

        if scope == "sent":
            qs = BookingService.list_for_requester(request.user, status_filter=status_filter)
        else:
            qs = BookingService.list_received(request.user, status_filter=status_filter)
        
        qs = qs.order_by("-created_at")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(BookingOfferSerializer(page, many=True).data)

    @extend_schema(
        summary="Create a booking offer",
        description="Create a new booking request targeting a specific user ID or an email address.",
        request=BookingOfferCreateSerializer,
        responses={201: BookingOfferSerializer}
    )
    def post(self, request):
        serializer = BookingOfferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target_user_id = data.pop("target_user_id", None)
        target_email = data.pop("target_email", "")
        offer = BookingService.create_offer(
            requester=request.user, target_user_id=target_user_id, target_email=target_email, **data
        )
        return Response(
            {"success": True, "offer": BookingOfferSerializer(offer).data, "message": "Booking request sent."},
            status=status.HTTP_201_CREATED,
        )


class BookingOfferAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Accept a booking offer",
        description="Accept a pending booking offer targeting the authenticated user.",
        request=None,
        responses={200: BookingOfferSerializer}
    )
    def post(self, request, offer_id: int):
        offer = BookingService.accept(target_user=request.user, offer_id=offer_id)
        return Response(
            {"success": True, "offer": BookingOfferSerializer(offer).data},
            status=status.HTTP_200_OK,
        )


class BookingOfferRejectView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Reject a booking offer",
        description="Reject a pending booking offer targeting the authenticated user.",
        request=None,
        responses={200: BookingOfferSerializer}
    )
    def post(self, request, offer_id: int):
        offer = BookingService.reject(target_user=request.user, offer_id=offer_id)
        return Response(
            {"success": True, "offer": BookingOfferSerializer(offer).data},
            status=status.HTTP_200_OK,
        )


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        kpis = DashboardService.kpis_for_user(request.user)
        return Response(
            {
                "success": True,
                "stats": kpis["stats"],
                "incoming_offers": BookingOfferSerializer(kpis["incoming_offers"], many=True).data,
                "upcoming_bookings": BookingOfferSerializer(kpis["upcoming_bookings"], many=True).data,
                "sent": kpis["sent"],
                "sent_offers": BookingOfferSerializer(kpis["sent_offers"], many=True).data,
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


class SendToUsersView(APIView):

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request):
        qs = User.objects.filter(is_active=True).order_by("name")

        search = request.query_params.get("search")
        if search:
            term = search.strip()
            qs = qs.filter(Q(name__icontains=term) | Q(email__icontains=term) | Q(phone__icontains=term))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(UserSerializer(page, many=True).data)
