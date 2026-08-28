from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from apps.common.pagination import StandardPagination
from .models import Performers
from .serializers import PerformerSearchSerializer

class PerformerSearchView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PerformerSearchSerializer
    pagination_class = StandardPagination

    @extend_schema(
        operation_id="seatgeek_performer_search",
        parameters=[
            OpenApiParameter(
                name="search",
                description="Search term to filter performers by name (case-insensitive partial match)",
                required=False,
                type=str,
            ),
        ],
        responses={200: PerformerSearchSerializer(many=True)},
    )
    def get(self, request):
        search_term = request.query_params.get("search", "")
        qs = Performers.objects.all()
        if search_term:
            qs = qs.filter(name__icontains=search_term)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(self.serializer_class(page, many=True).data)
