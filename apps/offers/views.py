from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.pagination import StandardPagination

from .models import Offer
from .serializers import (
    OfferCreateSerializer,
    OfferDocumentUploadSerializer,
    OfferSerializer,
    OfferShareSerializer,
    OfferSignSerializer,
    OfferUpdateSerializer,
)
from .services import OfferService


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "status",
                str,
                enum=[choice[0] for choice in Offer.Status.choices],
                required=False,
                description="Filter by offer status (e.g. status=rejected).",
            ),
            OpenApiParameter(
                "date_from",
                str,
                required=False,
                description="Event date lower bound, YYYY-MM-DD.",
            ),
            OpenApiParameter(
                "date_to",
                str,
                required=False,
                description="Event date upper bound, YYYY-MM-DD.",
            ),
            OpenApiParameter(
                "shared_with_me",
                bool,
                required=False,
                description="Only offers shared with me (directly or via a team) - excludes my own sent/received offers.",
            ),
        ],
        responses=OfferSerializer,
    ),
    post=extend_schema(request=OfferCreateSerializer, responses=OfferSerializer),
)
class OfferListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        params = self.request.query_params
        return OfferService.list_for(
            self.request.user,
            status=params.get("status"),
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            shared_with_me=params.get("shared_with_me", "").lower() == "true",
        )

    def get_serializer_class(self):
        return OfferCreateSerializer if self.request.method == "POST" else OfferSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        inquiry_id = data.pop("inquiry_id", None)
        receiver_id = data.pop("receiver_id", None)
        offer = OfferService.create(
            sender=request.user, inquiry_id=inquiry_id, receiver_id=receiver_id, **data
        )
        return Response(
            {"success": True, "offer": OfferSerializer(offer).data},
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    patch=extend_schema(request=OfferUpdateSerializer, responses=OfferSerializer),
)
class OfferDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return OfferService.get_for_viewer(self.request.user, self.kwargs["offer_id"])

    def get_serializer_class(self):
        return OfferUpdateSerializer if self.request.method == "PATCH" else OfferSerializer

    def retrieve(self, request, *args, **kwargs):
        offer = self.get_object()
        return Response({"success": True, "offer": OfferSerializer(offer).data})

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        offer = OfferService.update(
            actor=request.user,
            offer_id=self.kwargs["offer_id"],
            **serializer.validated_data,
        )
        return Response({"success": True, "offer": OfferSerializer(offer).data})


class OfferAcceptView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferSerializer

    def post(self, request, offer_id: int):
        offer = OfferService.respond(viewer=request.user, offer_id=offer_id, decision=Offer.Status.ACCEPTED)
        return Response({"success": True, "offer": OfferSerializer(offer).data})


class OfferRejectView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferSerializer

    def post(self, request, offer_id: int):
        offer = OfferService.respond(viewer=request.user, offer_id=offer_id, decision=Offer.Status.REJECTED)
        return Response({"success": True, "offer": OfferSerializer(offer).data})


class OfferShareView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferShareSerializer

    def post(self, request, offer_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offer = OfferService.share(
            actor=request.user,
            offer_id=offer_id,
            user_ids=serializer.validated_data.get("user_ids", []),
            team_ids=serializer.validated_data.get("team_ids", []),
        )
        return Response({"success": True, "offer": OfferSerializer(offer).data})


class OfferUnshareView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferShareSerializer

    def post(self, request, offer_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offer = OfferService.unshare(
            actor=request.user,
            offer_id=offer_id,
            user_ids=serializer.validated_data.get("user_ids", []),
            team_ids=serializer.validated_data.get("team_ids", []),
        )
        return Response({"success": True, "offer": OfferSerializer(offer).data})


class OfferSignView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferSignSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, offer_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        OfferService.add_signature(
            actor=request.user,
            offer_id=offer_id,
            signature=serializer.validated_data["signature"],
        )
        offer = OfferService.get_for_viewer(request.user, offer_id)
        return Response({"success": True, "offer": OfferSerializer(offer).data}, status=status.HTTP_201_CREATED)


class OfferDocumentUploadView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferDocumentUploadSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, offer_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        OfferService.add_documents(
            actor=request.user,
            offer_id=offer_id,
            files=serializer.validated_data["files"],
        )
        offer = OfferService.get_for_viewer(request.user, offer_id)
        return Response({"success": True, "offer": OfferSerializer(offer).data}, status=status.HTTP_201_CREATED)
