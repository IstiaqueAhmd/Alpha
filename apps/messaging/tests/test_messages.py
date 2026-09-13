from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.messaging.models import ConversationMember
from apps.messaging.services import ConversationService, MessageService

User = get_user_model()


def make_user(email: str, **kwargs) -> User:
    return User.objects.create_user(email=email, name=email.split("@")[0], password="pass12345", **kwargs)


class ApiTestCase(TestCase):
    def login_as(self, user) -> None:
        token = RefreshToken.for_user(user).access_token
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"


class MessageOwnershipTests(ApiTestCase):
    def setUp(self):
        self.alice = make_user("alice2@example.com")
        self.bob = make_user("bob2@example.com")
        self.conversation, _ = ConversationService.get_or_create_direct(viewer=self.alice, other_user_id=self.bob.pk)

    def test_send_updates_conversation_preview_and_marks_read_for_sender(self):
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="hi")

        conversation = ConversationService.get_for_viewer(self.alice, self.conversation.pk)
        self.assertEqual(conversation.last_message_id, message.pk)

        membership = ConversationMember.objects.get(conversation=conversation, user=self.alice)
        self.assertEqual(membership.last_read_message_id, message.pk)

    def test_unread_count_excludes_own_and_deleted_messages(self):
        MessageService.send(viewer=self.alice, conversation=self.conversation, body="one")
        deleted = MessageService.send(viewer=self.alice, conversation=self.conversation, body="two")
        MessageService.delete(viewer=self.alice, message=deleted)

        self.login_as(self.bob)
        url = reverse("messaging:conversation-detail", args=[self.conversation.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["conversation"]["unread_count"], 1)

    def test_only_sender_can_edit(self):
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="hi")

        with self.assertRaises(PermissionDenied):
            MessageService.edit(viewer=self.bob, message=message, body="hacked")

        MessageService.edit(viewer=self.alice, message=message, body="edited")
        message.refresh_from_db()
        self.assertEqual(message.body, "edited")
        self.assertTrue(message.is_edited)

    def test_only_sender_can_delete(self):
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="hi")

        with self.assertRaises(PermissionDenied):
            MessageService.delete(viewer=self.bob, message=message)

        MessageService.delete(viewer=self.alice, message=message)
        message.refresh_from_db()
        self.assertTrue(message.is_deleted)
        self.assertEqual(message.body, "")

    def test_cannot_edit_a_deleted_message(self):
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, body="hi")
        MessageService.delete(viewer=self.alice, message=message)
        with self.assertRaises(ValidationError):
            MessageService.edit(viewer=self.alice, message=message, body="edited")

    def test_reply_must_belong_to_same_conversation(self):
        carol = make_user("carol2@example.com")
        other_conversation, _ = ConversationService.get_or_create_direct(viewer=self.alice, other_user_id=carol.pk)
        foreign_message = MessageService.send(viewer=self.alice, conversation=other_conversation, body="elsewhere")

        with self.assertRaises(ValidationError):
            MessageService.send(
                viewer=self.alice, conversation=self.conversation, body="reply", reply_to_id=foreign_message.pk,
            )

    def test_non_participant_cannot_send(self):
        eve = make_user("eve2@example.com")
        with self.assertRaises(PermissionDenied):
            MessageService.send(viewer=eve, conversation=self.conversation, body="hi")


class AttachmentValidationTests(ApiTestCase):
    def setUp(self):
        self.alice = make_user("alice3@example.com")
        self.bob = make_user("bob3@example.com")
        self.conversation, _ = ConversationService.get_or_create_direct(viewer=self.alice, other_user_id=self.bob.pk)

    def test_rejects_disallowed_content_type(self):
        bad_file = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            MessageService.send(viewer=self.alice, conversation=self.conversation, files=[bad_file])

    def test_accepts_allowed_image(self):
        image = SimpleUploadedFile("photo.png", b"fake-bytes", content_type="image/png")
        message = MessageService.send(viewer=self.alice, conversation=self.conversation, files=[image])
        self.assertEqual(message.attachments.count(), 1)
        self.assertEqual(message.attachments.first().kind, "image")

    def test_send_via_rest_endpoint_with_multipart_upload(self):
        self.login_as(self.alice)
        url = reverse("messaging:messages", args=[self.conversation.pk])
        doc = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        # Plain django.test.Client multipart-encodes automatically when given
        # file objects and no explicit content_type (unlike DRF's APIClient,
        # this Client has no `format="multipart"` kwarg).
        response = self.client.post(url, {"body": "see attached", "files": [doc]})

        self.assertEqual(response.status_code, 201)
        payload = response.json()["message"]
        self.assertEqual(payload["body"], "see attached")
        self.assertEqual(len(payload["attachments"]), 1)
        self.assertEqual(payload["attachments"][0]["kind"], "file")
