from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.bookings.models import Activity

from .models import Conversation, Message, MessageAttachment


class ConversationService:
    @staticmethod
    def list_for(user: User, *, query: str | None = None) -> QuerySet[Conversation]:
        qs = (
            Conversation.objects
            .filter(participants=user)
            .prefetch_related("participants", "messages")
            .order_by("-last_message_at", "-created_at")
        )
        if query:
            qs = qs.filter(participants__name__icontains=query).distinct()
        return qs

    @classmethod
    def get_or_create_with(cls, *, viewer: User, other_user_id: int) -> Conversation:
        if viewer.pk == other_user_id:
            raise ValidationError("Cannot start a conversation with yourself.")
        other = User.objects.filter(pk=other_user_id, is_active=True).first()
        if not other:
            raise NotFound("User not found.")

        existing = (
            Conversation.objects
            .annotate(participant_count=Count("participants"))
            .filter(participants=viewer)
            .filter(participants=other)
            .filter(participant_count=2)
            .first()
        )
        if existing:
            return existing

        conversation = Conversation.objects.create()
        conversation.participants.add(viewer, other)
        return conversation

    @staticmethod
    def get_for_viewer(viewer: User, conversation_id: int) -> Conversation:
        conversation = (
            Conversation.objects
            .prefetch_related("participants")
            .filter(pk=conversation_id, participants=viewer)
            .first()
        )
        if not conversation:
            raise NotFound("Conversation not found.")
        return conversation


class MessageService:
    @classmethod
    @transaction.atomic
    def send(
        cls,
        *,
        viewer: User,
        conversation: Conversation,
        body: str = "",
        files=None,
    ) -> Message:
        if viewer not in conversation.participants.all():
            raise PermissionDenied("Not a participant in this conversation.")

        message = Message.objects.create(conversation=conversation, sender=viewer, body=body or "")

        files = files or []
        for upload in files:
            kind = (
                MessageAttachment.Kind.IMAGE
                if (getattr(upload, "content_type", "") or "").startswith("image/")
                else MessageAttachment.Kind.FILE
            )
            MessageAttachment.objects.create(
                message=message,
                kind=kind,
                file=upload,
                name=getattr(upload, "name", "")[:255],
                size_bytes=getattr(upload, "size", 0) or 0,
                content_type=getattr(upload, "content_type", "") or "",
            )

        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message_at", "updated_at"])

        for participant in conversation.participants.exclude(pk=viewer.pk):
            Activity.objects.create(
                user=participant,
                verb=Activity.Verb.MESSAGE_RECEIVED,
                summary="Message received",
                detail=f"From {viewer.name or viewer.email}",
                metadata={"conversation_id": conversation.pk, "message_id": message.pk},
            )
        return message

    @staticmethod
    def list_for_conversation(viewer: User, conversation: Conversation) -> QuerySet[Message]:
        if viewer not in conversation.participants.all():
            raise PermissionDenied("Not a participant in this conversation.")
        return (
            Message.objects
            .select_related("sender")
            .prefetch_related("attachments")
            .filter(conversation=conversation)
            .order_by("-created_at")
        )

    @staticmethod
    def mark_read(viewer: User, conversation: Conversation) -> int:
        if viewer not in conversation.participants.all():
            raise PermissionDenied("Not a participant in this conversation.")
        return (
            Message.objects
            .filter(conversation=conversation, read_at__isnull=True)
            .exclude(sender=viewer)
            .update(read_at=timezone.now())
        )
