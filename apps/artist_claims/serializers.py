from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import ArtistClaim, ArtistClaimDocument, ClaimStatus


class SeatgeekPerformerClaimSerializer(serializers.Serializer):
    """Minimal shape of a claimed SeatGeek performer - id is a string PK."""

    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    image = serializers.CharField(read_only=True)


class ArtistClaimDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtistClaimDocument
        fields = ["id", "file", "created_at"]
        read_only_fields = fields


class ArtistClaimSerializer(serializers.ModelSerializer):
    claimant = UserSerializer(read_only=True)
    artist_user = UserSerializer(read_only=True)
    seatgeek_performer = SeatgeekPerformerClaimSerializer(read_only=True)
    reviewed_by = UserSerializer(read_only=True)
    documents = ArtistClaimDocumentSerializer(many=True, read_only=True)
    target_type = serializers.CharField(read_only=True)

    class Meta:
        model = ArtistClaim
        fields = [
            "id",
            "claimant",
            "artist_user",
            "seatgeek_performer",
            "target_type",
            "agency_roster_url",
            "confirmation_email",
            "company_agency",
            "business_email",
            "adder_role",
            "representation",
            "note",
            "documents",
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "created_at",
        ]
        read_only_fields = fields


class ArtistClaimCreateSerializer(serializers.Serializer):
    artist_user_id = serializers.IntegerField(required=False)
    seatgeek_performer_id = serializers.CharField(required=False, max_length=191)

    agency_roster_url = serializers.URLField(max_length=500)
    confirmation_email = serializers.EmailField()
    company_agency = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    business_email = serializers.EmailField()
    adder_role = serializers.CharField(max_length=255)
    representation = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True, default="")

    documents = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        default=list,
        max_length=10,
    )

    def validate(self, attrs):
        has_artist_user = bool(attrs.get("artist_user_id"))
        has_performer = bool(attrs.get("seatgeek_performer_id"))
        if has_artist_user == has_performer:
            raise serializers.ValidationError("Provide exactly one of artist_user_id or seatgeek_performer_id.")
        return attrs


class ClaimReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ClaimedArtistSearchResultSerializer(serializers.Serializer):
    """Shape returned by the search API - one row per distinct claimed
    artist (internal user or SeatGeek performer), with every claimant on it.
    Built from plain dicts in ArtistClaimService.search_claimed_artists, not
    a queryset, so this is a plain Serializer, not a ModelSerializer.
    """

    source = serializers.ChoiceField(choices=["internal", "seatgeek"], read_only=True)
    artist_user_id = serializers.IntegerField(read_only=True, allow_null=True)
    seatgeek_performer_id = serializers.CharField(read_only=True, allow_null=True)
    name = serializers.CharField(read_only=True)
    claimed_by = serializers.ListField(read_only=True)
