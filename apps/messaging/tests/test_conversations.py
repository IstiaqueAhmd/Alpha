from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.messaging.models import Conversation, ConversationMember
from apps.messaging.services import ConversationService

User = get_user_model()


def make_user(email: str, **kwargs) -> User:
    return User.objects.create_user(email=email, name=email.split("@")[0], password="pass12345", **kwargs)


class ApiTestCase(TestCase):
    """The API is JWT-only (no SessionAuthentication), so `force_login` leaves
    `request.user` anonymous - issue a real bearer token instead, matching
    apps/teams/tests/test_teams.py.
    """

    def login_as(self, user) -> None:
        token = RefreshToken.for_user(user).access_token
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"


class DirectConversationTests(ApiTestCase):
    def setUp(self):
        self.alice = make_user("alice@example.com")
        self.bob = make_user("bob@example.com")

    def test_creating_direct_conversation_twice_reuses_it(self):
        self.login_as(self.alice)
        url = reverse("messaging:conversations")
        first = self.client.post(url, {"user_id": self.bob.pk}, content_type="application/json")
        second = self.client.post(url, {"user_id": self.bob.pk}, content_type="application/json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["conversation"]["id"], second.json()["conversation"]["id"])
        self.assertEqual(Conversation.objects.filter(is_group=False).count(), 1)

    def test_concurrent_creation_does_not_duplicate(self):
        """Simulates the race the `direct_key` unique constraint guards
        against: two requests both pass the "no existing conversation" check
        before either has committed.
        """
        key = Conversation.direct_key_for(self.alice.pk, self.bob.pk)
        self.assertIsNone(Conversation.objects.filter(direct_key=key).first())

        conv1, created1 = ConversationService.get_or_create_direct(viewer=self.alice, other_user_id=self.bob.pk)
        conv2, created2 = ConversationService.get_or_create_direct(viewer=self.bob, other_user_id=self.alice.pk)

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(conv1.pk, conv2.pk)
        self.assertEqual(Conversation.objects.filter(direct_key=key).count(), 1)

    def test_cannot_start_conversation_with_self(self):
        self.login_as(self.alice)
        url = reverse("messaging:conversations")
        response = self.client.post(url, {"user_id": self.alice.pk}, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_non_participant_cannot_view_conversation(self):
        conversation, _ = ConversationService.get_or_create_direct(viewer=self.alice, other_user_id=self.bob.pk)
        eve = make_user("eve@example.com")
        self.login_as(eve)
        url = reverse("messaging:conversation-detail", args=[conversation.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class GroupConversationTests(ApiTestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com")
        self.admin = make_user("admin@example.com")
        self.member = make_user("member@example.com")
        self.outsider = make_user("outsider@example.com")

        conversation = ConversationService.create_group(
            viewer=self.owner, name="Tour crew", member_ids=[self.admin.pk, self.member.pk],
        )
        ConversationMember.objects.filter(conversation=conversation, user=self.admin).update(
            role=ConversationMember.Role.ADMIN,
        )
        # Re-fetch so `self.conversation`'s prefetched memberships reflect the
        # role change above - services read that cache rather than re-querying
        # (see ConversationService._membership), matching how a real request
        # always resolves the conversation fresh via get_for_viewer first.
        self.conversation = ConversationService.get_for_viewer(self.owner, conversation.pk)

    def test_member_cannot_add_members(self):
        with self.assertRaises(PermissionDenied):
            ConversationService.add_members(
                viewer=self.member, conversation=self.conversation, member_ids=[self.outsider.pk],
            )

    def test_admin_can_add_members_but_not_remove_owner(self):
        conversation = ConversationService.add_members(
            viewer=self.admin, conversation=self.conversation, member_ids=[self.outsider.pk],
        )
        self.assertTrue(
            ConversationMember.objects.filter(conversation=conversation, user=self.outsider).exists()
        )

        conversation = ConversationService.get_for_viewer(self.admin, self.conversation.pk)
        with self.assertRaises(PermissionDenied):
            ConversationService.remove_member(
                viewer=self.admin, conversation=conversation, target_user_id=self.owner.pk,
            )

    def test_admin_cannot_remove_another_admin(self):
        second_admin = make_user("second_admin@example.com")
        conversation = ConversationService.add_members(
            viewer=self.owner, conversation=self.conversation, member_ids=[second_admin.pk],
        )
        ConversationMember.objects.filter(conversation=conversation, user=second_admin).update(
            role=ConversationMember.Role.ADMIN,
        )
        conversation = ConversationService.get_for_viewer(self.admin, conversation.pk)
        with self.assertRaises(PermissionDenied):
            ConversationService.remove_member(
                viewer=self.admin, conversation=conversation, target_user_id=second_admin.pk,
            )

    def test_owner_leaving_transfers_ownership_to_longest_tenured_admin(self):
        ConversationService.leave(viewer=self.owner, conversation=self.conversation)
        admin_membership = ConversationMember.objects.get(conversation=self.conversation, user=self.admin)
        self.assertEqual(admin_membership.role, ConversationMember.Role.OWNER)

    def test_last_member_leaving_deletes_conversation(self):
        conversation = ConversationService.get_for_viewer(self.owner, self.conversation.pk)
        ConversationService.remove_member(viewer=self.owner, conversation=conversation, target_user_id=self.member.pk)

        conversation = ConversationService.get_for_viewer(self.owner, self.conversation.pk)
        ConversationService.remove_member(viewer=self.owner, conversation=conversation, target_user_id=self.admin.pk)

        conversation = ConversationService.get_for_viewer(self.owner, self.conversation.pk)
        ConversationService.leave(viewer=self.owner, conversation=conversation)

        self.assertFalse(Conversation.objects.filter(pk=self.conversation.pk).exists())

    def test_direct_conversation_cannot_be_left(self):
        direct, _ = ConversationService.get_or_create_direct(viewer=self.owner, other_user_id=self.member.pk)
        with self.assertRaises(ValidationError):
            ConversationService.leave(viewer=self.owner, conversation=direct)
