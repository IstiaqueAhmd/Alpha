from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.teams.serializers import TeamSerializer

from .models import Offer, OfferDocument, OfferSignature

CONTRACT_FIELDS = (
    "artist_name",
    "date",
    "venue",
    "venue_address",
    "city_state_country_zip",
    "venue_phone",
    "offer_amount",
    "airfare",
    "backline",
    "hotel_ground_transportation",
    "catering",
    "first_class_sound_and_lighting",
    "door_time",
    "expected_attendance",
    "past_performers",
    "social_media_request",
    "what_is_event_for",
    "other_artists",
    "contact_signatory_name",
    "contact_signatory_address",
    "contact_signatory_contact_info",
    "contact_buyer_name",
    "contact_buyer_address",
    "contact_buyer_contact_info",
    "contact_production_name",
    "contact_production_contact_info",
    "additional_notes",
)


class OfferSignatureSerializer(serializers.ModelSerializer):
    signer = UserSerializer(read_only=True)

    class Meta:
        model = OfferSignature
        fields = ("id", "signer", "signature", "signed_at")
        read_only_fields = fields


class OfferDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferDocument
        fields = ("id", "document", "created_at")
        read_only_fields = fields


class OfferSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)
    shared_with_users = UserSerializer(many=True, read_only=True)
    shared_with_teams = TeamSerializer(many=True, read_only=True)
    signatures = OfferSignatureSerializer(many=True, read_only=True)
    documents = OfferDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = (
            "id",
            "uid",
            "inquiry",
            "sender",
            "receiver",
            "shared_with_users",
            "shared_with_teams",
            "status",
            "responded_at",
            *CONTRACT_FIELDS,
            "signatures",
            "documents",
            "created_at",
        )
        read_only_fields = (
            "id",
            "uid",
            "sender",
            "receiver",
            "shared_with_users",
            "shared_with_teams",
            "status",
            "responded_at",
            "signatures",
            "documents",
            "created_at",
        )


class OfferCreateSerializer(serializers.ModelSerializer):
    inquiry_id = serializers.IntegerField(required=False)
    receiver_id = serializers.IntegerField(required=False)
    signature = serializers.ImageField(required=False)
    files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        max_length=10,
    )

    class Meta:
        model = Offer
        fields = ("inquiry_id", "receiver_id", "signature", "files", *CONTRACT_FIELDS)

    def validate(self, attrs):
        if not attrs.get("inquiry_id") and not attrs.get("receiver_id"):
            raise serializers.ValidationError("Provide either inquiry_id or receiver_id.")
        if attrs.get("inquiry_id") and attrs.get("receiver_id"):
            raise serializers.ValidationError("Provide only one of inquiry_id or receiver_id, not both.")
        return attrs


class OfferUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = CONTRACT_FIELDS
        extra_kwargs = {field: {"required": False} for field in fields}


class OfferShareSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    team_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)

    def validate(self, attrs):
        if not attrs.get("user_ids") and not attrs.get("team_ids"):
            raise serializers.ValidationError("Provide at least one user_id or team_id.")
        return attrs


class OfferSignSerializer(serializers.Serializer):
    signature = serializers.ImageField()


class OfferDocumentUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        max_length=10,
    )
