from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import Conversation, Message, MessageAttachment

ONLINE_THRESHOLD = timedelta(minutes=5)


class MessageAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageAttachment
        fields = ("id", "kind", "file", "name", "size_bytes", "content_type")
        read_only_fields = ("id",)


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ("id", "conversation", "sender", "body", "read_at", "attachments", "created_at")
        read_only_fields = ("id", "sender", "read_at", "attachments", "created_at")


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(allow_blank=True, required=False)
    files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        max_length=10,
    )

    def validate(self, attrs):
        if not attrs.get("body") and not attrs.get("files"):
            raise serializers.ValidationError("Message must have a body or at least one attachment.")
        return attrs


class ConversationSerializer(serializers.ModelSerializer):
    participants = UserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    other_is_online = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "participants",
            "other_participant",
            "other_is_online",
            "last_message",
            "last_message_at",
            "unread_count",
            "created_at",
        )

    def _viewer(self):
        request = self.context.get("request")
        return request.user if request and request.user.is_authenticated else None

    def get_other_participant(self, obj):
        viewer = self._viewer()
        if not viewer:
            return None
        other = next((p for p in obj.participants.all() if p.pk != viewer.pk), None)
        return UserSerializer(other).data if other else None

    def get_other_is_online(self, obj) -> bool:
        viewer = self._viewer()
        if not viewer:
            return False
        other = next((p for p in obj.participants.all() if p.pk != viewer.pk), None)
        if not other or not other.last_seen_at:
            return False
        return (timezone.now() - other.last_seen_at) < ONLINE_THRESHOLD

    def get_last_message(self, obj):
        last = obj.messages.order_by("-created_at").first()
        return MessageSerializer(last).data if last else None

    def get_unread_count(self, obj) -> int:
        viewer = self._viewer()
        if not viewer:
            return 0
        return obj.messages.filter(read_at__isnull=True).exclude(sender=viewer).count()


class ConversationCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
