from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.pagination import StandardPagination

from apps.accounts.permissions import IsAdmin

from .models import Team
from .roles import ArtistRole, TeamDomain, hierarchy
from .serializers import (
    HierarchyRoleSerializer,
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationDeclineSerializer,
    MemberAddSerializer,
    ReviewSerializer,
    TeamCreateSerializer,
    TeamInvitationSerializer,
    TeamInvitationTokenSerializer,
    TeamMembershipSerializer,
    TeamSerializer,
    TeamUserSerializer,
)
from .services import ApprovalService, InvitationService, TeamService


# Per-role extra fields the add/invite endpoints require beyond user_id/email
# + role - see ArtistExtraFieldsMixin in serializers.py, which is the actual
# validation. This is just the same shape as reference data so a client can
# render the right form fields without hardcoding "artist is special"
# somewhere of its own. Roles absent here need nothing extra.
ROLE_EXTRA_FIELDS: dict[str, list[dict]] = {
    ArtistRole.ARTIST.value: [
        {
            "name": "agency_roster_url",
            "label": "Official agency/management roster URL",
            "type": "url",
            "required": True,
        },
        {
            "name": "confirmation_email",
            "label": "Artist confirmation email",
            "type": "email",
            "required": True,
        },
        {
            "name": "documents",
            "label": "Proof of representation",
            "type": "file[]",
            "required": True,
        },
        {
            "name": "note",
            "label": "Note",
            "type": "string",
            "required": False,
        },
    ],
}


class RoleHierarchyView(GenericAPIView):
    """Reference data: the role hierarchy for each domain, plus any extra
    fields a role needs on add/invite (see ROLE_EXTRA_FIELDS above).

    Lets a client render the role picker - and the right form fields once a
    role is picked - without hardcoding the hierarchy or the artist-only
    extra fields that roles.py / serializers.py already own.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = HierarchyRoleSerializer

    def get(self, request):
        domains = {}
        for domain in TeamDomain:
            rows = hierarchy(domain.value)
            for row in rows:
                row["extra_fields"] = ROLE_EXTRA_FIELDS.get(row["role"], [])
            domains[domain.value] = rows
        return Response(
            {"success": True, "domains": domains},
            status=status.HTTP_200_OK,
        )


class TeamListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamCreateSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = TeamService.list_for(request.user, search=request.query_params.get("search"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            TeamSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = TeamService.create(
            user=request.user,
            domain=serializer.validated_data["domain"],
            name=serializer.validated_data["name"],
            role=serializer.validated_data["role"],
        )
        return Response(
            {
                "success": True,
                "message": "Team created. Your membership is awaiting approval.",
                "team": TeamSerializer(team, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class RelatedUserSearchView(GenericAPIView):
    """Search users who share at least one approved team with the caller -
    e.g. picking a teammate to share something with, across any of my teams.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = TeamUserSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = TeamService.search_related_users(request.user, email=request.query_params.get("email"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(TeamUserSerializer(page, many=True).data)


class PublicUserSearchView(GenericAPIView):
    """Platform-wide user search, not scoped to a shared team."""

    permission_classes = [IsAuthenticated]
    serializer_class = TeamUserSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = TeamService.search_all_users(email=request.query_params.get("email"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(TeamUserSerializer(page, many=True).data)


class PublicTeamSearchView(GenericAPIView):
    """Platform-wide team search, not scoped to membership - approved teams only."""

    permission_classes = [IsAuthenticated]
    serializer_class = TeamSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = TeamService.search_public_teams(search=request.query_params.get("search"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            TeamSerializer(page, many=True, context={"request": request}).data
        )


class TeamDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamSerializer

    def get(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        return Response(
            {"success": True, "team": TeamSerializer(team, context={"request": request}).data},
            status=status.HTTP_200_OK,
        )

    def delete(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        TeamService.delete(actor=request.user, team=team)
        return Response({"success": True}, status=status.HTTP_200_OK)


class TeamMemberListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MemberAddSerializer
    pagination_class = StandardPagination

    def get(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        qs = TeamService.list_members(team, search=request.query_params.get("search"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response(
            TeamMembershipSerializer(page, many=True).data
        )
        response.data["counts"] = TeamService.member_counts(team)
        return response

    def post(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = TeamService.add_member(
            actor=request.user,
            team=team,
            user_id=serializer.validated_data["user_id"],
            role=serializer.validated_data["role"],
            agency_roster_url=serializer.validated_data.get("agency_roster_url"),
            confirmation_email=serializer.validated_data.get("confirmation_email"),
            note=serializer.validated_data.get("note", ""),
            documents=serializer.validated_data.get("documents"),
        )
        return Response(
            {
                "success": True,
                "message": "Member submitted for approval.",
                "membership": TeamMembershipSerializer(membership).data,
            },
            status=status.HTTP_201_CREATED,
        )


class TeamMemberDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamMembershipSerializer

    def delete(self, request, team_id: int, membership_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        TeamService.remove_member(
            actor=request.user, team=team, membership_id=membership_id
        )
        return Response({"success": True}, status=status.HTTP_200_OK)


class TeamInvitationListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvitationCreateSerializer
    pagination_class = StandardPagination

    def get(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        qs = InvitationService.list_for_team(team)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        # Token included: the caller is an approved member of the issuing team.
        return paginator.get_paginated_response(
            TeamInvitationTokenSerializer(page, many=True).data
        )

    def post(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = InvitationService.create(
            actor=request.user,
            team=team,
            email=serializer.validated_data["email"],
            role=serializer.validated_data["role"],
            agency_roster_url=serializer.validated_data.get("agency_roster_url"),
            confirmation_email=serializer.validated_data.get("confirmation_email"),
            note=serializer.validated_data.get("note", ""),
            documents=serializer.validated_data.get("documents"),
        )
        return Response(
            {
                "success": True,
                "message": "Invitation sent.",
                "invitation": TeamInvitationTokenSerializer(invitation).data,
            },
            status=status.HTTP_201_CREATED,
        )


class TeamInvitationRevokeView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamInvitationSerializer

    def post(self, request, team_id: int, invitation_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        invitation = InvitationService.revoke(
            actor=request.user, team=team, invitation_id=invitation_id
        )
        return Response(
            {"success": True, "invitation": TeamInvitationSerializer(invitation).data},
            status=status.HTTP_200_OK,
        )


class InvitationAcceptView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvitationAcceptSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = InvitationService.accept(
            user=request.user, token=serializer.validated_data["token"]
        )
        return Response(
            {
                "success": True,
                "message": "Invitation accepted. Your membership is awaiting approval.",
                "membership": TeamMembershipSerializer(membership).data,
            },
            status=status.HTTP_200_OK,
        )


class InvitationDeclineView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvitationDeclineSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = InvitationService.decline(
            user=request.user, token=serializer.validated_data["token"]
        )
        return Response(
            {
                "success": True,
                "message": "Invitation declined.",
                "invitation": TeamInvitationSerializer(invitation).data,
            },
            status=status.HTTP_200_OK,
        )


# --- Superuser review queue --------------------------------------------------


class MembershipReviewListView(GenericAPIView):
    """Superadmin review queue. Teams are auto-approved on creation, so this
    is just memberships - no separate team or invitation review step.

    Defaults to the pending queue; `?status=approved` or `?status=rejected`
    browses reviewed history instead.
    """

    permission_classes = [IsAdmin]
    serializer_class = TeamMembershipSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = ApprovalService.list_memberships(status=request.query_params.get("status"))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            TeamMembershipSerializer(page, many=True).data
        )


class MembershipReviewDetailView(GenericAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ReviewSerializer

    def get(self, request, membership_id: int):
        membership = ApprovalService.get_membership(membership_id)
        return Response(
            {"success": True, "membership": TeamMembershipSerializer(membership).data},
            status=status.HTTP_200_OK,
        )

    def post(self, request, membership_id: int):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = ApprovalService.review_membership(
            reviewer=request.user,
            membership_id=membership_id,
            approve=serializer.validated_data["approve"],
            note=serializer.validated_data.get("note", ""),
        )
        return Response(
            {"success": True, "membership": TeamMembershipSerializer(membership).data},
            status=status.HTTP_200_OK,
        )


