from rest_framework import serializers

from .models import AvailDate, AvailEntry, AvailList, AvailShare


# ---------------------------------------------------------------------------
# Read-only helpers
# ---------------------------------------------------------------------------


class AvailListOwnerSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class AvailDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailDate
        fields = ["id", "date"]
        read_only_fields = fields


class AvailEntryArtistSerializer(serializers.Serializer):
    """Lightweight artist info pulled from the User record."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    image = serializers.ImageField(read_only=True)


class AvailEntrySerializer(serializers.ModelSerializer):
    artist = AvailEntryArtistSerializer(read_only=True)
    dates = AvailDateSerializer(many=True, read_only=True)
    open_dates = serializers.SerializerMethodField()

    class Meta:
        model = AvailEntry
        fields = [
            "id",
            "artist",
            "genre",
            "location",
            "note",
            "position",
            "open_dates",
            "dates",
            "created_at",
        ]
        read_only_fields = fields

    def get_open_dates(self, obj: AvailEntry) -> int:
        # Use prefetched cache when available, else count.
        dates = getattr(obj, "_prefetched_dates", None)
        if dates is not None:
            return len(dates)
        return obj.dates.count()


class AvailShareSerializer(serializers.ModelSerializer):
    shared_by = AvailListOwnerSerializer(read_only=True)
    shared_with = AvailListOwnerSerializer(read_only=True)

    class Meta:
        model = AvailShare
        fields = [
            "id",
            "shared_by",
            "shared_with",
            "shared_email",
            "message",
            "created_at",
        ]
        read_only_fields = fields


class AvailListSerializer(serializers.ModelSerializer):
    owner = AvailListOwnerSerializer(read_only=True)
    entry_count = serializers.SerializerMethodField()

    class Meta:
        model = AvailList
        fields = [
            "id",
            "owner",
            "name",
            "description",
            "visibility",
            "entry_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_entry_count(self, obj: AvailList) -> int:
        # Use annotated value when available.
        count = getattr(obj, "_entry_count", None)
        if count is not None:
            return count
        return obj.entries.count()


class AvailListDetailSerializer(AvailListSerializer):
    """Extended serializer that includes entries inline."""

    entries = AvailEntrySerializer(many=True, read_only=True)

    class Meta(AvailListSerializer.Meta):
        fields = AvailListSerializer.Meta.fields + ["entries"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Write serializers
# ---------------------------------------------------------------------------


class AvailListCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    visibility = serializers.ChoiceField(
        choices=[("public", "Public"), ("private", "Private")],
        default="private",
    )


class AvailListUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    visibility = serializers.ChoiceField(
        choices=[("public", "Public"), ("private", "Private")],
        required=False,
    )


class AvailEntryCreateSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    genre = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    location = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
    dates = serializers.ListField(
        child=serializers.DateField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class AvailEntryUpdateSerializer(serializers.Serializer):
    genre = serializers.CharField(max_length=255, required=False, allow_blank=True)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    position = serializers.IntegerField(required=False, min_value=0)


class AvailEntryUpdateDatesSerializer(serializers.Serializer):
    """Bulk-replace all dates for an entry."""

    dates = serializers.ListField(
        child=serializers.DateField(),
        allow_empty=True,
    )


class AvailShareCreateSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=list
    )
    emails = serializers.ListField(
        child=serializers.EmailField(), required=False, allow_empty=True, default=list
    )
    message = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("user_ids") and not attrs.get("emails"):
            raise serializers.ValidationError(
                "Either user_ids or emails must be provided."
            )
        return attrs
