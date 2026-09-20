from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.bookings.models import Activity

from .events import broadcast_to_users
from .models import Conversation, ConversationMember, Message, MessageAttachment
from .serializers import ConversationSerializer, MessageSerializer, UserSerializer
from .validators import is_image, validate_attachment

Role = ConversationMember.Role


def _user_snapshot(user: User) -> dict:
    """Name/email as of the event, not a live reference - a later rename
    shouldn't rewrite what a system message said at the time.
    """
    return {"id": user.pk, "name": user.name, "email": user.email}


def _system_message_body(event: str, actor: User, target: User | None) -> str:
    actor_name = actor.name or actor.email
    target_name = (target.name or target.email) if target else None
    if event == "member_added":
        return f"{actor_name} added {target_name}"
    if event == "member_removed":
        return f"{actor_name} removed {target_name}"
    if event == "member_left":
        return f"{actor_name} left the group"
    if event == "member_joined":
        return f"{actor_name} joined the group"
    if event == "member_removed_from_team":
        return f"{actor_name} was removed from the group"
    return event


def _write_system_message(*, conversation: Conversation, actor: User, event: str, target: User | None = None) -> Message:
    """Post a kind=SYSTEM message recording a membership event (added/removed/
    left/joined) - `body` is a plain-English fallback, `system_event` carries
    structured actor/target snapshots for clients that want to render their own
    UI (avatars, i18n, etc). No unread/Activity bookkeeping here - these are
    informational, not something an inbox badge should count.
    """
    message = Message.objects.create(
        conversation=conversation,
        sender=actor,
        kind=Message.Kind.SYSTEM,
        body=_system_message_body(event, actor, target),
        system_event={
            "event": event,
            "actor": _user_snapshot(actor),
            "target": _user_snapshot(target) if target else None,
        },
    )
    conversation.last_message = message
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=["last_message", "last_message_at", "updated_at"])
    return message


class ConversationService:
    @staticmethod
    def list_for(user: User, *, query: str | None = None) -> QuerySet[Conversation]:
        qs = (
            Conversation.objects
            .filter(memberships__user=user)
            .prefetch_related("memberships__user", "last_message__sender", "last_message__attachments")
            .order_by("-last_message_at", "-created_at")
        )
        if query:
            qs = qs.filter(
                Q(name__icontains=query) | Q(memberships__user__name__icontains=query)
            )
        return qs.distinct()

    @staticmethod
    def _membership(conversation: Conversation, user_id: int) -> ConversationMember | None:
        """Reads from `conversation.memberships`' prefetch cache when one is
        loaded (the normal case - views always resolve the conversation via
        `get_for_viewer` first), falling back to a query otherwise.
        """
        return next((m for m in conversation.memberships.all() if m.user_id == user_id), None)

    @classmethod
    def _require_role(cls, conversation: Conversation, user: User, allowed_roles: set) -> ConversationMember:
        membership = cls._membership(conversation, user.pk)
        if not membership:
            raise PermissionDenied("Not a participant in this conversation.")
        if membership.role not in allowed_roles:
            raise PermissionDenied("You do not have permission to do this.")
        return membership

    @classmethod
    @transaction.atomic
    def get_or_create_direct(cls, *, viewer: User, other_user_id: int) -> tuple[Conversation, bool]:
        if viewer.pk == other_user_id:
            raise ValidationError("Cannot start a conversation with yourself.")
        other = User.objects.filter(pk=other_user_id, is_active=True).first()
        if not other:
            raise NotFound("User not found.")

        direct_key = Conversation.direct_key_for(viewer.pk, other_user_id)
        existing = Conversation.objects.filter(direct_key=direct_key).first()
        if existing:
            return existing, False

        try:
            with transaction.atomic():
                conversation = Conversation.objects.create(
                    is_group=False, direct_key=direct_key, created_by=viewer,
                )
                ConversationMember.objects.bulk_create([
                    ConversationMember(conversation=conversation, user=viewer, role=Role.MEMBER),
                    ConversationMember(conversation=conversation, user=other, role=Role.MEMBER),
                ])
        except IntegrityError:
            # Lost a race against a concurrent request creating the same pair.
            return Conversation.objects.get(direct_key=direct_key), False

        conversation = cls.get_for_viewer(viewer, conversation.pk)
        broadcast_to_users([viewer.pk, other.pk], "conversation.created", ConversationSerializer(conversation).data)
        return conversation, True

    @classmethod
    @transaction.atomic
    def create_group(cls, *, viewer: User, name: str, member_ids: list[int]) -> Conversation:
        member_ids = {mid for mid in member_ids if mid != viewer.pk}
        members = list(User.objects.filter(pk__in=member_ids, is_active=True))
        if not members:
            raise ValidationError("Add at least one other member.")

        conversation = Conversation.objects.create(is_group=True, name=name.strip(), created_by=viewer)
        ConversationMember.objects.bulk_create(
            [ConversationMember(conversation=conversation, user=viewer, role=Role.OWNER)]
            + [ConversationMember(conversation=conversation, user=u, role=Role.MEMBER) for u in members]
        )

        conversation = cls.get_for_viewer(viewer, conversation.pk)
        all_ids = [viewer.pk] + [u.pk for u in members]
        broadcast_to_users(all_ids, "conversation.created", ConversationSerializer(conversation).data)
        return conversation

    @staticmethod
    def get_for_viewer(viewer: User, conversation_id: int) -> Conversation:
        conversation = (
            Conversation.objects
            .prefetch_related("memberships__user", "last_message__sender", "last_message__attachments")
            .filter(pk=conversation_id, memberships__user=viewer)
            .first()
        )
        if not conversation:
            raise NotFound("Conversation not found.")
        return conversation

    @staticmethod
    def get_for_team_viewer(viewer: User, team_id: int) -> Conversation:
        """A team's auto-managed group conversation, for a caller who is
        already one of its members. Same 404-for-everything-else shape as
        `get_for_viewer` - team not found, no group yet, or viewer not a
        member all look identical from the outside.
        """
        conversation = (
            Conversation.objects
            .prefetch_related("memberships__user", "last_message__sender", "last_message__attachments")
            .filter(team_id=team_id, memberships__user=viewer)
            .first()
        )
        if not conversation:
            raise NotFound("Team chat not found.")
        return conversation

    @classmethod
    @transaction.atomic
    def rename(cls, *, viewer: User, conversation: Conversation, name: str) -> Conversation:
        if not conversation.is_group:
            raise ValidationError("Only group conversations can be renamed.")
        if conversation.team_id:
            raise ValidationError("This group follows its team's name and can't be renamed directly.")
        cls._require_role(conversation, viewer, {Role.OWNER, Role.ADMIN})

        conversation.name = name.strip()
        conversation.save(update_fields=["name", "updated_at"])

        member_ids = [m.user_id for m in conversation.memberships.all()]
        broadcast_to_users(member_ids, "conversation.updated", ConversationSerializer(conversation).data)
        return conversation

    @classmethod
    @transaction.atomic
    def add_members(cls, *, viewer: User, conversation: Conversation, member_ids: list[int]) -> Conversation:
        if not conversation.is_group:
            raise ValidationError("Only group conversations support adding members.")
        if conversation.team_id:
            raise ValidationError("Membership in a team's group follows the team roster and can't be edited directly.")
        cls._require_role(conversation, viewer, {Role.OWNER, Role.ADMIN})

        existing_ids = {m.user_id for m in conversation.memberships.all()}
        candidate_ids = {mid for mid in member_ids if mid not in existing_ids}
        new_users = list(User.objects.filter(pk__in=candidate_ids, is_active=True))
        if not new_users:
            raise ValidationError("No new users to add - check the member ids.")

        ConversationMember.objects.bulk_create(
            [ConversationMember(conversation=conversation, user=u, role=Role.MEMBER) for u in new_users]
        )

        conversation = cls.get_for_viewer(viewer, conversation.pk)
        all_member_ids = [m.user_id for m in conversation.memberships.all()]

        for user in new_users:
            broadcast_to_users(
                all_member_ids, "member.added",
                {"conversation_id": conversation.pk, "user": UserSerializer(user).data, "role": Role.MEMBER},
            )
            system_message = _write_system_message(
                conversation=conversation, actor=viewer, event="member_added", target=user,
            )
            broadcast_to_users(all_member_ids, "message.created", MessageSerializer(system_message).data)

        broadcast_to_users([u.pk for u in new_users], "conversation.created", ConversationSerializer(conversation).data)
        return conversation

    @classmethod
    @transaction.atomic
    def remove_member(cls, *, viewer: User, conversation: Conversation, target_user_id: int) -> Conversation | None:
        if not conversation.is_group:
            raise ValidationError("Only group conversations support removing members.")
        if conversation.team_id:
            raise ValidationError("Membership in a team's group follows the team roster and can't be edited directly.")
        if target_user_id == viewer.pk:
            raise ValidationError("Use the leave endpoint to remove yourself.")

        actor_membership = cls._require_role(conversation, viewer, {Role.OWNER, Role.ADMIN})
        target_membership = cls._membership(conversation, target_user_id)
        if not target_membership:
            raise NotFound("That user is not a member of this conversation.")
        if target_membership.role == Role.OWNER:
            raise PermissionDenied("The owner cannot be removed.")
        if actor_membership.role == Role.ADMIN and target_membership.role != Role.MEMBER:
            raise PermissionDenied("Admins can only remove regular members.")

        target_user = target_membership.user
        target_membership.delete()
        remaining_ids = [m.user_id for m in conversation.memberships.all() if m.user_id != target_user_id]
        payload = {"conversation_id": conversation.pk, "user_id": target_user_id}

        if not remaining_ids:
            conversation.delete()
            broadcast_to_users([target_user_id], "member.removed", payload)
            return None

        broadcast_to_users(remaining_ids + [target_user_id], "member.removed", payload)
        system_message = _write_system_message(
            conversation=conversation, actor=viewer, event="member_removed", target=target_user,
        )
        broadcast_to_users(remaining_ids, "message.created", MessageSerializer(system_message).data)
        return conversation

    @classmethod
    @transaction.atomic
    def leave(cls, *, viewer: User, conversation: Conversation) -> None:
        if not conversation.is_group:
            raise ValidationError("Direct conversations can't be left.")
        if conversation.team_id:
            raise ValidationError("You can't leave a team's group directly - leave the team instead.")

        membership = cls._membership(conversation, viewer.pk)
        if not membership:
            raise PermissionDenied("Not a participant in this conversation.")

        other_memberships = [m for m in conversation.memberships.all() if m.user_id != viewer.pk]

        if membership.role == Role.OWNER and other_memberships:
            successor = (
                min((m for m in other_memberships if m.role == Role.ADMIN), key=lambda m: m.created_at, default=None)
                or min(other_memberships, key=lambda m: m.created_at)
            )
            successor.role = Role.OWNER
            successor.save(update_fields=["role", "updated_at"])

        membership.delete()

        if not other_memberships:
            conversation.delete()
            return

        remaining_ids = [m.user_id for m in other_memberships]
        broadcast_to_users(remaining_ids, "member.left", {"conversation_id": conversation.pk, "user_id": viewer.pk})
        system_message = _write_system_message(conversation=conversation, actor=viewer, event="member_left")
        broadcast_to_users(remaining_ids, "message.created", MessageSerializer(system_message).data)

    @classmethod
    def mark_read(cls, *, viewer: User, conversation: Conversation) -> int | None:
        membership = cls._membership(conversation, viewer.pk)
        if not membership:
            raise PermissionDenied("Not a participant in this conversation.")

        latest_id = conversation.messages.order_by("-id").values_list("id", flat=True).first()
        if latest_id and (not membership.last_read_message_id or latest_id > membership.last_read_message_id):
            membership.last_read_message_id = latest_id
            membership.save(update_fields=["last_read_message", "updated_at"])

        member_ids = [m.user_id for m in conversation.memberships.all()]
        broadcast_to_users(member_ids, "conversation.read", {
            "conversation_id": conversation.pk,
            "user_id": viewer.pk,
            "last_read_message_id": membership.last_read_message_id,
        })
        return membership.last_read_message_id

    @staticmethod
    def get_or_create_team_conversation(team) -> Conversation:
        """The one auto-managed group conversation for `team`, creating it on
        first use. Called from `apps.teams.services` as members are approved -
        never from a view, so no permission check applies here.
        """
        conversation = Conversation.objects.filter(team=team).first()
        if conversation:
            return conversation
        try:
            with transaction.atomic():
                return Conversation.objects.create(
                    is_group=True, team=team, name=team.name, created_by=team.created_by
                )
        except IntegrityError:
            # Lost a race against a concurrent approval creating the same team's group.
            return Conversation.objects.get(team=team)

    @classmethod
    @transaction.atomic
    def sync_add_team_member(cls, *, team, user: User) -> None:
        """Add `user` to `team`'s auto-managed group. Idempotent - approving an
        already-added member (shouldn't happen, but cheap to guard) is a no-op.
        """
        conversation = cls.get_or_create_team_conversation(team)
        _, created = ConversationMember.objects.get_or_create(
            conversation=conversation, user=user, defaults={"role": Role.MEMBER}
        )
        if not created:
            return

        conversation = cls.get_for_viewer(user, conversation.pk)
        all_member_ids = [m.user_id for m in conversation.memberships.all()]
        broadcast_to_users(
            all_member_ids, "member.added",
            {"conversation_id": conversation.pk, "user": UserSerializer(user).data, "role": Role.MEMBER},
        )
        broadcast_to_users([user.pk], "conversation.created", ConversationSerializer(conversation).data)

        system_message = _write_system_message(conversation=conversation, actor=user, event="member_joined")
        broadcast_to_users(all_member_ids, "message.created", MessageSerializer(system_message).data)

    @classmethod
    @transaction.atomic
    def sync_remove_team_member(cls, *, team, user: User) -> None:
        """Remove `user` from `team`'s auto-managed group, if one exists yet."""
        conversation = Conversation.objects.filter(team=team).first()
        if not conversation:
            return
        deleted, _ = ConversationMember.objects.filter(conversation=conversation, user=user).delete()
        if not deleted:
            return

        remaining_ids = [
            m.user_id for m in conversation.memberships.all() if m.user_id != user.pk
        ]
        broadcast_to_users(
            remaining_ids + [user.pk], "member.removed",
            {"conversation_id": conversation.pk, "user_id": user.pk},
        )

        if remaining_ids:
            system_message = _write_system_message(
                conversation=conversation, actor=user, event="member_removed_from_team",
            )
            broadcast_to_users(remaining_ids, "message.created", MessageSerializer(system_message).data)

    @classmethod
    def get_dm_for_offer(cls, *, sender: User, conversation_id: int) -> tuple[Conversation, int]:
        """Resolve a `conversation_id` passed alongside an offer create request.

        Offers can only be sent through a DM, never a group - a chat offer is a
        two-party negotiation, so `receiver_id` must unambiguously be "the other
        person in this conversation". Returns the conversation plus that other
        user's id, for the caller to cross-check against `receiver_id`/`inquiry`.
        """
        conversation = cls.get_for_viewer(sender, conversation_id)
        if conversation.is_group:
            raise ValidationError("Offers can only be sent in a direct conversation.")
        other = next((m for m in conversation.memberships.all() if m.user_id != sender.pk), None)
        if not other:
            raise ValidationError("This conversation has no other participant to send an offer to.")
        return conversation, other.user_id


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
        reply_to_id: int | None = None,
    ) -> Message:
        membership = ConversationService._membership(conversation, viewer.pk)
        if not membership:
            raise PermissionDenied("Not a participant in this conversation.")

        files = files or []
        for upload in files:
            validate_attachment(upload)

        reply_to = None
        if reply_to_id:
            reply_to = conversation.messages.filter(pk=reply_to_id).first()
            if not reply_to:
                raise ValidationError("reply_to_id does not reference a message in this conversation.")

        message = Message.objects.create(
            conversation=conversation, sender=viewer, body=body or "", reply_to=reply_to,
        )
        for upload in files:
            MessageAttachment.objects.create(
                message=message,
                kind=MessageAttachment.Kind.IMAGE if is_image(upload) else MessageAttachment.Kind.FILE,
                file=upload,
                name=(getattr(upload, "name", "") or "")[:255],
                size_bytes=getattr(upload, "size", 0) or 0,
                content_type=getattr(upload, "content_type", "") or "",
            )

        conversation.last_message = message
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message", "last_message_at", "updated_at"])

        # Sending implicitly marks read for the sender (no unread badge on your own message).
        membership.last_read_message = message
        membership.save(update_fields=["last_read_message", "updated_at"])

        other_member_ids = [m.user_id for m in conversation.memberships.all() if m.user_id != viewer.pk]
        for uid in other_member_ids:
            Activity.objects.create(
                user_id=uid,
                verb=Activity.Verb.MESSAGE_RECEIVED,
                summary="Message received",
                detail=f"From {viewer.name or viewer.email}",
                metadata={"conversation_id": conversation.pk, "message_id": message.pk},
            )

        broadcast_to_users(other_member_ids + [viewer.pk], "message.created", MessageSerializer(message).data)
        return message

    @classmethod
    @transaction.atomic
    def create_offer_message(cls, *, conversation: Conversation, sender: User, offer) -> Message:
        """Post `offer` into `conversation` as a chat bubble.

        Called from `apps.offers.services.OfferService.create` right after the
        offer itself is created - `apps.messaging.services.ConversationService
        .get_dm_for_offer` has already checked `sender` belongs to this (direct)
        conversation, so this only does the message-side bookkeeping `send()`
        does, minus attachments/replies (an offer message carries neither).
        """
        membership = ConversationService._membership(conversation, sender.pk)
        if not membership:
            raise PermissionDenied("Not a participant in this conversation.")

        message = Message.objects.create(
            conversation=conversation, sender=sender, kind=Message.Kind.OFFER, offer=offer,
        )

        conversation.last_message = message
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message", "last_message_at", "updated_at"])

        membership.last_read_message = message
        membership.save(update_fields=["last_read_message", "updated_at"])

        other_member_ids = [m.user_id for m in conversation.memberships.all() if m.user_id != sender.pk]
        for uid in other_member_ids:
            Activity.objects.create(
                user_id=uid,
                verb=Activity.Verb.MESSAGE_RECEIVED,
                summary="Offer received",
                detail=f"From {sender.name or sender.email}",
                metadata={"conversation_id": conversation.pk, "message_id": message.pk, "offer_id": offer.pk},
            )

        broadcast_to_users(other_member_ids + [sender.pk], "message.created", MessageSerializer(message).data)
        return message

    @staticmethod
    def get_for_viewer(viewer: User, message_id: int) -> Message:
        message = (
            Message.objects
            .select_related("sender", "reply_to__sender", "conversation")
            .prefetch_related("attachments", "conversation__memberships")
            .filter(pk=message_id)
            .first()
        )
        if not message:
            raise NotFound("Message not found.")
        if not ConversationService._membership(message.conversation, viewer.pk):
            raise PermissionDenied("Not a participant in this conversation.")
        return message

    @staticmethod
    @transaction.atomic
    def edit(*, viewer: User, message: Message, body: str) -> Message:
        if message.sender_id != viewer.pk:
            raise PermissionDenied("You can only edit your own messages.")
        if message.is_deleted:
            raise ValidationError("Cannot edit a deleted message.")

        message.body = body
        message.is_edited = True
        message.edited_at = timezone.now()
        message.save(update_fields=["body", "is_edited", "edited_at", "updated_at"])

        member_ids = [m.user_id for m in message.conversation.memberships.all()]
        broadcast_to_users(member_ids, "message.updated", MessageSerializer(message).data)
        return message

    @staticmethod
    @transaction.atomic
    def delete(*, viewer: User, message: Message) -> Message:
        if message.sender_id != viewer.pk:
            raise PermissionDenied("You can only delete your own messages.")
        if message.is_deleted:
            return message

        for attachment in message.attachments.all():
            attachment.file.delete(save=False)
            attachment.delete()

        message.body = ""
        message.is_deleted = True
        message.deleted_at = timezone.now()
        message.save(update_fields=["body", "is_deleted", "deleted_at", "updated_at"])

        member_ids = [m.user_id for m in message.conversation.memberships.all()]
        broadcast_to_users(member_ids, "message.deleted", {
            "conversation_id": message.conversation_id,
            "message_id": message.pk,
            "deleted_at": message.deleted_at.isoformat(),
        })
        return message

    @staticmethod
    def list_for_conversation(viewer: User, conversation: Conversation) -> QuerySet[Message]:
        if not ConversationService._membership(conversation, viewer.pk):
            raise PermissionDenied("Not a participant in this conversation.")
        return (
            Message.objects
            .select_related("sender", "reply_to__sender")
            .prefetch_related("attachments")
            .filter(conversation=conversation)
            .order_by("-created_at")
        )
