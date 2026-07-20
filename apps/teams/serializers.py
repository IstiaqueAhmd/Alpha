from rest_framework import serializers

from .models import Team, TeamInvitation, TeamMembership
from .roles import ROLE_CHOICES, TeamDomain, rank_of


class TeamUserSerializer(serializers.Serializer):

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class TeamSerializer(serializers.ModelSerializer):
    created_by = TeamUserSerializer(read_only=True)

    class Meta:
        model = Team
        fields = [
            "id",
            "domain",
            "name",
            "status",
            "created_by",
            "approved_at",
            "review_note",
            "created_at",
        ]
        read_only_fields = fields


class TeamCreateSerializer(serializers.Serializer):
    domain = serializers.ChoiceField(choices=TeamDomain.choices)
    name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=ROLE_CHOICES)


class TeamMembershipSerializer(serializers.ModelSerializer):
    user = TeamUserSerializer(read_only=True)
    rank = serializers.SerializerMethodField()
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_domain = serializers.CharField(source="team.domain", read_only=True)

    class Meta:
        model = TeamMembership
        fields = [
            "id",
            "team",
            "team_name",
            "team_domain",
            "user",
            "role",
            "role_label",
            "rank",
            "status",
            "approved_at",
            "review_note",
            "created_at",
        ]
        read_only_fields = fields

    def get_rank(self, obj: TeamMembership) -> int:
        # `obj.team` is select_related by every service that lists memberships,
        # so this does not re-query per row.
        return rank_of(obj.team.domain, obj.role)


class MemberAddSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=ROLE_CHOICES)


class TeamInvitationSerializer(serializers.ModelSerializer):
    invited_by = TeamUserSerializer(read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = TeamInvitation
        fields = [
            "id",
            "team",
            "email",
            "role",
            "role_label",
            "status",
            "expires_at",
            "accepted_at",
            "invited_by",
            "created_at",
        ]
        read_only_fields = fields


class TeamInvitationTokenSerializer(TeamInvitationSerializer):
    class Meta(TeamInvitationSerializer.Meta):
        fields = TeamInvitationSerializer.Meta.fields + ["token"]
        read_only_fields = fields


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=ROLE_CHOICES)


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)


class ReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class HierarchyRoleSerializer(serializers.Serializer):
    role = serializers.CharField()
    label = serializers.CharField()
    rank = serializers.IntegerField()
