from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.pagination import StandardPagination

from .models import Inquiry
from .serializers import InquiryCreateSerializer, InquirySerializer
from .services import InquiryService


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "status",
                str,
                enum=[choice[0] for choice in Inquiry.Status.choices],
                required=False,
                description="Filter by inquiry status.",
            ),
        ],
        responses=InquirySerializer,
    ),
    post=extend_schema(request=InquiryCreateSerializer, responses=InquirySerializer),
)
class InquiryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        return InquiryService.list_for(self.request.user, status=self.request.query_params.get("status"))

    def get_serializer_class(self):
        return InquiryCreateSerializer if self.request.method == "POST" else InquirySerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inquiry = InquiryService.create(sender=request.user, **serializer.validated_data)
        return Response(
            {"success": True, "inquiry": InquirySerializer(inquiry).data},
            status=status.HTTP_201_CREATED,
        )


class InquiryDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InquirySerializer

    def get_object(self):
        return InquiryService.get_for_viewer(self.request.user, self.kwargs["inquiry_id"])

    def retrieve(self, request, *args, **kwargs):
        inquiry = self.get_object()
        return Response({"success": True, "inquiry": InquirySerializer(inquiry).data})


class InquiryAcceptView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InquirySerializer

    def post(self, request, inquiry_id: int):
        inquiry = InquiryService.respond(viewer=request.user, inquiry_id=inquiry_id, decision=Inquiry.Status.ACCEPTED)
        return Response({"success": True, "inquiry": InquirySerializer(inquiry).data})


class InquiryDeclineView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InquirySerializer

    def post(self, request, inquiry_id: int):
        inquiry = InquiryService.respond(viewer=request.user, inquiry_id=inquiry_id, decision=Inquiry.Status.DECLINED)
        return Response({"success": True, "inquiry": InquirySerializer(inquiry).data})
