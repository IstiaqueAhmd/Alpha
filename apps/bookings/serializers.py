from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import Activity, AvailabilitySlot, BookingOffer


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilitySlot
        fields = ("id", "date", "status", "note")
        read_only_fields = ("id",)


class AvailabilitySlotUpsertSerializer(serializers.Serializer):
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=AvailabilitySlot.Status.choices)
    note = serializers.CharField(max_length=255, allow_blank=True, required=False)


class BookingOfferSerializer(serializers.ModelSerializer):
    requester = UserSerializer(read_only=True)
    artist = UserSerializer(read_only=True)

    class Meta:
        model = BookingOffer
        fields = (
            "id",
            "requester",
            "artist",
            "title",
            "event_date",
            "event_time",
            "venue_name",
            "address",
            "amount_cents",
            "budget_min_cents",
            "budget_max_cents",
            "contact_name",
            "contact_email",
            "contact_phone",
            "notes",
            "status",
            "decided_at",
            "created_at",
        )
        read_only_fields = ("id", "requester", "artist", "status", "decided_at", "created_at")


class BookingOfferCreateSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    title = serializers.CharField(max_length=255)
    event_date = serializers.DateField()
    event_time = serializers.TimeField(required=False, allow_null=True)
    venue_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    address = serializers.CharField(max_length=255, allow_blank=True, required=False)
    amount_cents = serializers.IntegerField(min_value=0, required=False)
    budget_min_cents = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    budget_max_cents = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    contact_name = serializers.CharField(max_length=255, allow_blank=True, required=False)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=32, allow_blank=True, required=False)
    notes = serializers.CharField(allow_blank=True, required=False)

    def validate(self, attrs):
        lo = attrs.get("budget_min_cents")
        hi = attrs.get("budget_max_cents")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"budget_max_cents": "Must be >= budget_min_cents."})
        return attrs


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ("id", "verb", "summary", "detail", "metadata", "created_at")
        read_only_fields = fields
