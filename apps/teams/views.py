from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.pagination import StandardPagination

from .models import Team
from .permissions import IsSuperUser
from .roles import TeamDomain, hierarchy
from .serializers import (
    HierarchyRoleSerializer,
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    MemberAddSerializer,
    ReviewSerializer,
    TeamCreateSerializer,
    TeamInvitationSerializer,
    TeamInvitationTokenSerializer,
    TeamMembershipSerializer,
    TeamSerializer,
)
from .services import ApprovalService, InvitationService, TeamService


class RoleHierarchyView(GenericAPIView):
    """Reference data: the role hierarchy for each domain.

    Lets a client render the role picker without hardcoding the hierarchy that
    roles.py already owns. Flat list per domain, each row carries its rank.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = HierarchyRoleSerializer

    def get(self, request):
        return Response(
            {
                "success": True,
                "domains": {
                    domain.value: hierarchy(domain.value) for domain in TeamDomain
                },
            },
            status=status.HTTP_200_OK,
        )


class TeamListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamCreateSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = TeamService.list_for(request.user)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(TeamSerializer(page, many=True).data)

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
                "team": TeamSerializer(team).data,
            },
            status=status.HTTP_201_CREATED,
        )


class TeamDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamSerializer

    def get(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        return Response(
            {"success": True, "team": TeamSerializer(team).data},
            status=status.HTTP_200_OK,
        )


class TeamMemberListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MemberAddSerializer
    pagination_class = StandardPagination

    def get(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        qs = TeamService.list_members(team)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            TeamMembershipSerializer(page, many=True).data
        )

    def post(self, request, team_id: int):
        team = TeamService.get_for_member(request.user, team_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = TeamService.add_member(
            actor=request.user,
            team=team,
            user_id=serializer.validated_data["user_id"],
            role=serializer.validated_data["role"],
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


# --- Superuser review queue --------------------------------------------------


class PendingReviewView(GenericAPIView):
    permission_classes = [IsSuperUser]
    serializer_class = TeamSerializer

    def get(self, request):
        # Teams are auto-approved on creation, so the queue is just
        # memberships now - no separate team or invitation review step.
        return Response(
            {
                "success": True,
                "memberships": TeamMembershipSerializer(
                    ApprovalService.pending_memberships(), many=True
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class MembershipReviewView(GenericAPIView):
    permission_classes = [IsSuperUser]
    serializer_class = ReviewSerializer

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


