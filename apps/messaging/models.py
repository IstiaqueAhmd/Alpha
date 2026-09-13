from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Conversation(TimeStampedModel):
    """A message thread: either a 1-to-1 DM or a named group.

    `direct_key` is only ever set for 1-to-1 conversations - it's a
    deterministic ``"<lower_user_id>_<higher_user_id>"`` string with a DB
    unique constraint, which is what actually prevents two concurrent
    "start a DM with this person" requests from creating duplicate
    conversations (a plain query-then-create has a race; a unique column
    doesn't). Group conversations never set it.
    """

    is_group = models.BooleanField(default=False)
    name = models.CharField(max_length=255, blank=True)
    direct_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ConversationMember",
        related_name="conversations",
    )
    last_message = models.ForeignKey(
        "Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "conversations"
        ordering = ("-last_message_at", "-created_at")

    def __str__(self) -> str:
        return f"Conversation<{self.pk}>"

    @staticmethod
    def direct_key_for(user_id_a: int, user_id_b: int) -> str:
        lo, hi = sorted((user_id_a, user_id_b))
        return f"{lo}_{hi}"


class ConversationMember(TimeStampedModel):
    """Per-user membership row: role + read pointer.

    `last_read_message` (rather than a timestamp) drives unread counts -
    comparing message ids avoids any clock-skew issues and lets the count be
    a simple indexed ``id__gt`` filter.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_memberships",
    )
    role = models.CharField(max_length=8, choices=Role.choices, default=Role.MEMBER)
    last_read_message = models.ForeignKey(
        "Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "conversation_members"
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="uniq_conversation_member"),
        ]
        indexes = [
            models.Index(fields=["user", "conversation"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.conversation_id} ({self.role})"


class Message(TimeStampedModel):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    body = models.TextField(blank=True)
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "messages"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["conversation", "-created_at"]),
            models.Index(fields=["conversation", "id"]),
            models.Index(fields=["sender", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Message<{self.pk}> in {self.conversation_id}"


class MessageAttachment(TimeStampedModel):
    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        FILE = "file", "File"

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    file = models.FileField(upload_to="messages/attachments/")
    name = models.CharField(max_length=255, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "message_attachments"

    def __str__(self) -> str:
        return f"Attachment<{self.pk}> on {self.message_id}"
