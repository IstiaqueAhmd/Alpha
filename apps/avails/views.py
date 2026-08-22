from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.pagination import StandardPagination

from .serializers import (
    AvailEntryCreateSerializer,
    AvailEntrySerializer,
    AvailEntryUpdateDatesSerializer,
    AvailEntryUpdateSerializer,
    AvailListCreateSerializer,
    AvailListDetailSerializer,
    AvailListSerializer,
    AvailListUpdateSerializer,
    AvailShareCreateSerializer,
    AvailShareSerializer,
)
from .services import AvailEntryService, AvailListService, AvailShareService


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


class AvailListView(GenericAPIView):
    """Owner's own avail lists."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailListCreateSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = AvailListService.list_owned(
            request.user, search=request.query_params.get("search")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            AvailListSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        avail_list = AvailListService.create(
            owner=request.user,
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
            visibility=serializer.validated_data.get("visibility", "private"),
        )
        return Response(
            {
                "success": True,
                "message": "Avail list created.",
                "avail_list": AvailListSerializer(avail_list).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AvailListSharedView(GenericAPIView):
    """Lists shared with the current user."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailListSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = AvailListService.list_shared_with(
            request.user, search=request.query_params.get("search")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            AvailListSerializer(page, many=True).data
        )


class AvailListSentView(GenericAPIView):
    """Lists the current user has shared out."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailListSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = AvailListService.list_sent(
            request.user, search=request.query_params.get("search")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            AvailListSerializer(page, many=True).data
        )


class AvailListPublicView(GenericAPIView):
    """Browse public avail lists."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailListSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = AvailListService.list_public(
            search=request.query_params.get("search")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            AvailListSerializer(page, many=True).data
        )


class AvailListDetailView(GenericAPIView):
    """View, update, or delete a single avail list."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailListUpdateSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return super().get_permissions()

    def get(self, request, list_id: int):
        avail_list = AvailListService.get_with_entries(request.user, list_id)
        return Response(
            {
                "success": True,
                "avail_list": AvailListDetailSerializer(avail_list).data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, list_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        avail_list = AvailListService.update(
            request.user, list_id, **serializer.validated_data
        )
        return Response(
            {
                "success": True,
                "avail_list": AvailListSerializer(avail_list).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, list_id: int):
        AvailListService.delete(request.user, list_id)
        return Response({"success": True}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Entries (artists in a list)
# ---------------------------------------------------------------------------


class AvailEntryListCreateView(GenericAPIView):
    """List or add artists in an avail list."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailEntryCreateSerializer
    pagination_class = StandardPagination

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return super().get_permissions()

    def get(self, request, list_id: int):
        qs = AvailEntryService.list_entries(
            request.user, list_id, search=request.query_params.get("search")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            AvailEntrySerializer(page, many=True).data
        )

    def post(self, request, list_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = AvailEntryService.add_entry(
            user=request.user,
            list_id=list_id,
            artist_id=serializer.validated_data["artist_id"],
            genre=serializer.validated_data.get("genre", ""),
            location=serializer.validated_data.get("location", ""),
            note=serializer.validated_data.get("note", ""),
            dates=serializer.validated_data.get("dates"),
        )
        return Response(
            {
                "success": True,
                "message": "Artist added to list.",
                "entry": AvailEntrySerializer(entry).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AvailEntryDetailView(GenericAPIView):
    """Update or remove an artist from an avail list."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailEntryUpdateSerializer

    def patch(self, request, list_id: int, entry_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = AvailEntryService.update_entry(
            user=request.user,
            list_id=list_id,
            entry_id=entry_id,
            **serializer.validated_data,
        )
        return Response(
            {
                "success": True,
                "entry": AvailEntrySerializer(entry).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, list_id: int, entry_id: int):
        AvailEntryService.remove_entry(
            user=request.user, list_id=list_id, entry_id=entry_id
        )
        return Response({"success": True}, status=status.HTTP_200_OK)


class AvailEntryDatesView(GenericAPIView):
    """Bulk-replace available dates for an artist entry."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailEntryUpdateDatesSerializer

    def put(self, request, list_id: int, entry_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = AvailEntryService.update_dates(
            user=request.user,
            list_id=list_id,
            entry_id=entry_id,
            dates=serializer.validated_data["dates"],
        )
        return Response(
            {
                "success": True,
                "entry": AvailEntrySerializer(entry).data,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------------


class AvailShareListCreateView(GenericAPIView):
    """List or create shares for an avail list."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailShareCreateSerializer
    pagination_class = StandardPagination

    def get(self, request, list_id: int):
        qs = AvailShareService.list_shares(request.user, list_id)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            AvailShareSerializer(page, many=True).data
        )

    def post(self, request, list_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shares = AvailShareService.share_bulk(
            user=request.user,
            list_id=list_id,
            user_ids=serializer.validated_data.get("user_ids", []),
            emails=serializer.validated_data.get("emails", []),
            message=serializer.validated_data.get("message", ""),
        )
        return Response(
            {
                "success": True,
                "message": "List shared successfully.",
                "shares": AvailShareSerializer(shares, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AvailShareDetailView(GenericAPIView):
    """Remove a share from an avail list."""

    permission_classes = [IsAuthenticated]
    serializer_class = AvailShareSerializer

    def delete(self, request, list_id: int, share_id: int):
        AvailShareService.unshare(
            user=request.user, list_id=list_id, share_id=share_id
        )
        return Response({"success": True}, status=status.HTTP_200_OK)
