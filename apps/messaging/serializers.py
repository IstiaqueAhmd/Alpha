from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.offers.models import Offer

from .models import Conversation, ConversationMember, Message, MessageAttachment
from .presence import PresenceService
from .validators import MAX_FILES_PER_MESSAGE


class OfferChatPreviewSerializer(serializers.ModelSerializer):
    """Just enough to render an offer as a chat bubble - full details live at
    the existing offer detail endpoint, which the client opens by `id`.
    """

    class Meta:
        model = Offer
        fields = ("id", "uid", "status", "artist_name", "date", "venue", "offer_amount")
        read_only_fields = fields


class MessageAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageAttachment
        fields = ("id", "kind", "file", "name", "size_bytes", "content_type")
        read_only_fields = fields


class ReplyPreviewSerializer(serializers.ModelSerializer):
    """Compact one-level preview of the message being replied to - never
    recurses into its own `reply_to`, so a reply chain doesn't nest.
    """

    sender = UserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ("id", "sender", "body", "is_deleted", "created_at")
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    reply_to = ReplyPreviewSerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    offer = OfferChatPreviewSerializer(read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "conversation",
            "sender",
            "kind",
            "body",
            "reply_to",
            "is_edited",
            "edited_at",
            "is_deleted",
            "attachments",
            "offer",
            "system_event",
            "created_at",
        )
        read_only_fields = (
            "id", "sender", "kind", "is_edited", "edited_at", "is_deleted",
            "attachments", "offer", "system_event", "created_at",
        )


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(allow_blank=True, required=False)
    files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        max_length=MAX_FILES_PER_MESSAGE,
    )
    reply_to_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs.get("body") and not attrs.get("files"):
            raise serializers.ValidationError("Message must have a body or at least one attachment.")
        return attrs


class MessageUpdateSerializer(serializers.Serializer):
    body = serializers.CharField(allow_blank=False)


class ConversationMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    is_online = serializers.SerializerMethodField()

    class Meta:
        model = ConversationMember
        fields = ("user", "role", "is_online", "created_at")
        read_only_fields = fields

    def get_is_online(self, obj) -> bool:
        return PresenceService.is_online(obj.user_id)


class ConversationSerializer(serializers.ModelSerializer):
    members = ConversationMemberSerializer(source="memberships", many=True, read_only=True)
    last_message = MessageSerializer(read_only=True)
    unread_count = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    other_is_online = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "is_group",
            "name",
            "members",
            "my_role",
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

    def _viewer_membership(self, obj) -> ConversationMember | None:
        viewer = self._viewer()
        if not viewer:
            return None
        return next((m for m in obj.memberships.all() if m.user_id == viewer.pk), None)

    def get_my_role(self, obj) -> str | None:
        membership = self._viewer_membership(obj)
        return membership.role if membership else None

    def get_other_participant(self, obj):
        if obj.is_group:
            return None
        viewer = self._viewer()
        if not viewer:
            return None
        other = next((m.user for m in obj.memberships.all() if m.user_id != viewer.pk), None)
        return UserSerializer(other).data if other else None

    def get_other_is_online(self, obj) -> bool:
        if obj.is_group:
            return False
        viewer = self._viewer()
        if not viewer:
            return False
        other = next((m for m in obj.memberships.all() if m.user_id != viewer.pk), None)
        return PresenceService.is_online(other.user_id) if other else False

    def get_unread_count(self, obj) -> int:
        membership = self._viewer_membership(obj)
        if not membership:
            return 0
        qs = obj.messages.filter(is_deleted=False).exclude(sender_id=membership.user_id)
        if membership.last_read_message_id:
            qs = qs.filter(id__gt=membership.last_read_message_id)
        return qs.count()


class ConversationCreateSerializer(serializers.Serializer):
    """Handles both shapes: `{"user_id": N}` for a 1-to-1 DM, or
    `{"is_group": true, "name": "...", "member_ids": [...]}` for a group.
    """

    is_group = serializers.BooleanField(required=False, default=False)
    user_id = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    member_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True,
    )

    def validate(self, attrs):
        if attrs.get("is_group"):
            if not attrs.get("name", "").strip():
                raise serializers.ValidationError("Group conversations require a name.")
            if not attrs.get("member_ids"):
                raise serializers.ValidationError("Group conversations require at least one other member.")
        else:
            if not attrs.get("user_id"):
                raise serializers.ValidationError("user_id is required to start a direct conversation.")
        return attrs


class ConversationRenameSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, allow_blank=False)


class ConversationMemberAddSerializer(serializers.Serializer):
    member_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False,
    )
