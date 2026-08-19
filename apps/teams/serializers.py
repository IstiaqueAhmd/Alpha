import json
from rest_framework import serializers

from .models import (
    ArtistRepresentationDetails,
    MembershipDocument,
    Team,
    TeamInvitation,
    TeamMembership,
)
from .roles import ROLE_CHOICES, ArtistRole, TeamDomain, rank_of


class TeamUserSerializer(serializers.Serializer):

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class TeamSerializer(serializers.ModelSerializer):
    created_by = TeamUserSerializer(read_only=True)
    my_membership = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "domain",
            "name",
            "status",
            "created_by",
            "my_membership",
            "approved_at",
            "review_note",
            "created_at",
        ]
        read_only_fields = fields

    def get_my_membership(self, obj: Team) -> dict | None:
        """The caller's own membership on this team - role, domain-relative rank, and
        approval status - so the frontend can pick a dashboard on team switch without a
        second request. None if the caller was never a member (or the request has no
        authenticated user, e.g. schema generation).
        """
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return None

        membership = (
            TeamMembership.objects.filter(team=obj, user=request.user)
            .order_by("-created_at")
            .first()
        )
        if not membership:
            return None

        return {
            "role": membership.role,
            "role_label": membership.get_role_display(),
            "rank": rank_of(obj.domain, membership.role),
            "status": membership.status,
        }


class TeamCreateSerializer(serializers.Serializer):
    domain = serializers.ChoiceField(choices=TeamDomain.choices)
    name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=ROLE_CHOICES)


class MembershipDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipDocument
        fields = ["id", "file", "created_at"]
        read_only_fields = fields


class ArtistRepresentationDetailsSerializer(serializers.ModelSerializer):

    class Meta:
        model = ArtistRepresentationDetails
        fields = [
            "agency_roster_url",
            "confirmation_email",
            "company_agency",
            "business_email",
            "adder_role",
            "representation",
            "note",
        ]
        read_only_fields = fields


class ArtistDetailsInputSerializer(serializers.Serializer):
    """Nested payload strictly validated for the `artist` role."""

    agency_roster_url = serializers.URLField(max_length=500)
    confirmation_email = serializers.EmailField()
    company_agency = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    business_email = serializers.EmailField()
    adder_role = serializers.CharField(max_length=255)
    representation = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class TeamMembershipSerializer(serializers.ModelSerializer):

    user = TeamUserSerializer(read_only=True)
    rank = serializers.SerializerMethodField()
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    team_domain = serializers.CharField(source="team.domain", read_only=True)
    artist_representation_details = serializers.SerializerMethodField()
    documents = MembershipDocumentSerializer(many=True, read_only=True)

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
            "artist_representation_details",
            "documents",
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

    def get_artist_representation_details(self, obj: TeamMembership) -> dict | None:
        # None for every role but artist, and for artist rows added before
        # this existed.
        details = getattr(obj, "artist_representation_details", None)
        if details is None:
            return None
        return ArtistRepresentationDetailsSerializer(details).data


class MemberAddSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    details = serializers.JSONField(required=False, default=dict)
    documents = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        default=list,
        max_length=10,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        role = attrs.get("role")
        details = attrs.get("details", {})
        
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except ValueError:
                raise serializers.ValidationError({"details": "Must be a valid JSON object."})
                
        if not isinstance(details, dict):
            raise serializers.ValidationError({"details": "Must be a JSON object."})
            
        if role == ArtistRole.ARTIST.value:
            details_serializer = ArtistDetailsInputSerializer(data=details)
            if not details_serializer.is_valid():
                raise serializers.ValidationError({"details": details_serializer.errors})
                
            attrs["details"] = details_serializer.validated_data
        else:
            attrs["details"] = {}
            
        return attrs


class TeamInvitationSerializer(serializers.ModelSerializer):
    invited_by = TeamUserSerializer(read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    artist_representation_details = serializers.SerializerMethodField()
    documents = MembershipDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = TeamInvitation
        fields = [
            "id",
            "team",
            "email",
            "role",
            "role_label",
            "artist_representation_details",
            "documents",
            "status",
            "expires_at",
            "accepted_at",
            "invited_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_artist_representation_details(self, obj: TeamInvitation) -> dict | None:
        # Staged here only until acceptance, when it's re-parented onto the
        # resulting membership - see InvitationService._materialize.
        details = getattr(obj, "artist_representation_details", None)
        if details is None:
            return None
        return ArtistRepresentationDetailsSerializer(details).data


class TeamInvitationTokenSerializer(TeamInvitationSerializer):
    class Meta(TeamInvitationSerializer.Meta):
        fields = TeamInvitationSerializer.Meta.fields + ["token"]
        read_only_fields = fields


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    details = serializers.JSONField(required=False, default=dict)
    documents = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        default=list,
        max_length=10,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        role = attrs.get("role")
        details = attrs.get("details", {})
        
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except ValueError:
                raise serializers.ValidationError({"details": "Must be a valid JSON object."})
                
        if not isinstance(details, dict):
            raise serializers.ValidationError({"details": "Must be a JSON object."})
            
        if role == ArtistRole.ARTIST.value:
            details_serializer = ArtistDetailsInputSerializer(data=details)
            if not details_serializer.is_valid():
                raise serializers.ValidationError({"details": details_serializer.errors})
                
            attrs["details"] = details_serializer.validated_data
        else:
            attrs["details"] = {}
            
        return attrs


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)


class InvitationDeclineSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)


class ReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RoleExtraFieldSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    type = serializers.CharField()
    required = serializers.BooleanField()


class HierarchyRoleSerializer(serializers.Serializer):
    role = serializers.CharField()
    label = serializers.CharField()
    rank = serializers.IntegerField()
    extra_fields = RoleExtraFieldSerializer(many=True)
