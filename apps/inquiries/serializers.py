from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import Inquiry


class InquirySerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)

    class Meta:
        model = Inquiry
        fields = (
            "id",
            "uid",
            "sender",
            "receiver",
            "receiver_email",
            "event_title",
            "start_date_time",
            "expected_attendance",
            "budget",
            "full_name",
            "email",
            "phone_number",
            "additional_notes",
            "status",
            "created_at",
        )
        read_only_fields = ("id", "uid", "sender", "receiver", "status", "created_at")


class InquiryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inquiry
        fields = (
            "receiver_email",
            "event_title",
            "start_date_time",
            "expected_attendance",
            "budget",
            "full_name",
            "email",
            "phone_number",
            "additional_notes",
        )
