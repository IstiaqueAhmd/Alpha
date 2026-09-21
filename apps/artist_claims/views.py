from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin
from apps.common.pagination import StandardPagination

from .serializers import (
    ArtistClaimCreateSerializer,
    ArtistClaimSerializer,
    ClaimedArtistSearchResultSerializer,
    ClaimReviewSerializer,
)
from .services import ArtistClaimService


class ArtistClaimListCreateView(GenericAPIView):
    """My own claims - file a new one, or list the ones I've filed."""

    permission_classes = [IsAuthenticated]
    serializer_class = ArtistClaimCreateSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = ArtistClaimService.list_for(request.user, status=request.query_params.get("status"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            ArtistClaimSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        claim = ArtistClaimService.create(
            claimant=request.user,
            artist_user_id=data.pop("artist_user_id", None),
            seatgeek_performer_id=data.pop("seatgeek_performer_id", None),
            documents=data.pop("documents", None),
            **data,
        )
        return Response(
            {"success": True, "claim": ArtistClaimSerializer(claim, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )


class ArtistClaimDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ArtistClaimSerializer

    def get(self, request, claim_id: int):
        claim = ArtistClaimService.get_for_viewer(request.user, claim_id)
        return Response({"success": True, "claim": ArtistClaimSerializer(claim, context={"request": request}).data})

    def delete(self, request, claim_id: int):
        ArtistClaimService.withdraw(viewer=request.user, claim_id=claim_id)
        return Response({"success": True}, status=status.HTTP_200_OK)


class ClaimedArtistSearchView(GenericAPIView):
    """Search artists *from the claim table* - see
    ArtistClaimService.search_claimed_artists for the "why" behind that.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ClaimedArtistSearchResultSerializer

    def get(self, request):
        rows = ArtistClaimService.search_claimed_artists(
            search=request.query_params.get("search"),
            status=request.query_params.get("status"),
        )
        return Response({
            "success": True,
            "count": len(rows),
            "results": ClaimedArtistSearchResultSerializer(rows, many=True, context={"request": request}).data,
        })


class ClaimReviewListView(GenericAPIView):
    """Superadmin review queue. Defaults to the pending queue; `?status=approved`
    or `?status=rejected` browses reviewed history instead.
    """

    permission_classes = [IsAdmin]
    serializer_class = ArtistClaimSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = ArtistClaimService.list_review_queue(status=request.query_params.get("status"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            ArtistClaimSerializer(page, many=True, context={"request": request}).data
        )


class ClaimReviewDetailView(GenericAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClaimReviewSerializer

    def get(self, request, claim_id: int):
        claim = ArtistClaimService.get_for_review(claim_id)
        return Response({"success": True, "claim": ArtistClaimSerializer(claim, context={"request": request}).data})

    def post(self, request, claim_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        claim = ArtistClaimService.review(
            reviewer=request.user,
            claim_id=claim_id,
            approve=serializer.validated_data["approve"],
            note=serializer.validated_data.get("note", ""),
        )
        return Response({"success": True, "claim": ArtistClaimSerializer(claim, context={"request": request}).data})
