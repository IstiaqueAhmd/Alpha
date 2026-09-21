from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.messaging.models import Conversation, ConversationMember, Message
from apps.messaging.services import ConversationService
from apps.teams.models import ApprovalStatus, Team, TeamMembership
from apps.teams.roles import ArtistRole, TeamDomain
from apps.teams.services import ApprovalService, TeamService

User = get_user_model()


def make_user(email: str, **kwargs) -> User:
    return User.objects.create_user(email=email, name=email.split("@")[0], password="pass12345", **kwargs)


class GroupMembershipSystemMessageTests(TestCase):
    """Every membership change on a normal (non-team) group should also land
    in the message stream as a kind=system message, per `_write_system_message`
    in apps.messaging.services.
    """

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
        self.conversation = ConversationService.get_for_viewer(self.owner, conversation.pk)

    def test_adding_a_member_posts_a_system_message(self):
        conversation = ConversationService.add_members(
            viewer=self.owner, conversation=self.conversation, member_ids=[self.outsider.pk],
        )
        system_message = Message.objects.filter(
            conversation=conversation, kind=Message.Kind.SYSTEM,
        ).latest("created_at")

        self.assertEqual(system_message.system_event["event"], "member_added")
        self.assertEqual(system_message.system_event["actor"]["id"], self.owner.pk)
        self.assertEqual(system_message.system_event["target"]["id"], self.outsider.pk)
        self.assertIn(self.owner.name, system_message.body)
        self.assertIn(self.outsider.name, system_message.body)
        self.assertEqual(conversation.last_message_id, system_message.pk)

    def test_removing_a_member_posts_a_system_message(self):
        conversation = ConversationService.remove_member(
            viewer=self.owner, conversation=self.conversation, target_user_id=self.member.pk,
        )
        system_message = Message.objects.filter(
            conversation=conversation, kind=Message.Kind.SYSTEM,
        ).latest("created_at")

        self.assertEqual(system_message.system_event["event"], "member_removed")
        self.assertEqual(system_message.system_event["actor"]["id"], self.owner.pk)
        self.assertEqual(system_message.system_event["target"]["id"], self.member.pk)

    def test_leaving_posts_a_system_message_with_no_target(self):
        ConversationService.leave(viewer=self.member, conversation=self.conversation)
        system_message = Message.objects.filter(
            conversation=self.conversation, kind=Message.Kind.SYSTEM,
        ).latest("created_at")

        self.assertEqual(system_message.system_event["event"], "member_left")
        self.assertEqual(system_message.system_event["actor"]["id"], self.member.pk)
        self.assertIsNone(system_message.system_event["target"])

    def test_last_member_leaving_deletes_conversation_without_error(self):
        """No system message can be posted once the conversation itself is
        gone - the early-return path (empty membership) must not attempt it.
        """
        conversation = ConversationService.remove_member(
            viewer=self.owner, conversation=self.conversation, target_user_id=self.member.pk,
        )
        conversation = ConversationService.get_for_viewer(self.owner, conversation.pk)
        conversation = ConversationService.remove_member(
            viewer=self.owner, conversation=conversation, target_user_id=self.admin.pk,
        )
        conversation = ConversationService.get_for_viewer(self.owner, conversation.pk)
        ConversationService.leave(viewer=self.owner, conversation=conversation)

        self.assertFalse(Conversation.objects.filter(pk=self.conversation.pk).exists())

    def test_regular_text_message_is_not_a_system_message(self):
        from apps.messaging.services import MessageService

        message = MessageService.send(viewer=self.owner, conversation=self.conversation, body="hello")
        self.assertEqual(message.kind, Message.Kind.TEXT)
        self.assertIsNone(message.system_event)


class TeamGroupSystemMessageTests(TestCase):
    """The auto-managed team group posts the same kind of system message,
    driven by team approval/removal rather than a direct chat action.
    """

    def setUp(self):
        self.founder = make_user("founder@example.com")
        self.superuser = make_user("root@example.com", is_superuser=True, is_staff=True)
        self.recruit = make_user("recruit@example.com")
        self.team = Team.objects.create(
            domain=TeamDomain.ARTIST, name="Team A", created_by=self.founder, status=ApprovalStatus.APPROVED,
        )
        self.founder_membership = TeamMembership.objects.create(
            team=self.team, user=self.founder, role=ArtistRole.MANAGER, status=ApprovalStatus.PENDING,
        )

    def test_approving_a_membership_posts_a_joined_system_message(self):
        # Founder's own approval creates the group; approving a second member
        # exercises the "post into an existing group" path, matching the
        # normal case (nobody's chat starts empty).
        ApprovalService.review_membership(reviewer=self.superuser, membership_id=self.founder_membership.id, approve=True)

        membership = TeamMembership.objects.create(
            team=self.team, user=self.recruit, role=ArtistRole.TOUR_MANAGER, status=ApprovalStatus.PENDING,
        )
        ApprovalService.review_membership(reviewer=self.superuser, membership_id=membership.id, approve=True)

        conversation = Conversation.objects.get(team=self.team)
        system_message = Message.objects.filter(
            conversation=conversation, kind=Message.Kind.SYSTEM, system_event__event="member_joined",
        ).latest("created_at")
        self.assertEqual(system_message.system_event["actor"]["id"], self.recruit.pk)
        self.assertIn(self.recruit.name, system_message.body)

    def test_rejecting_a_membership_does_not_create_a_group_or_message(self):
        membership = TeamMembership.objects.create(
            team=self.team, user=self.recruit, role=ArtistRole.TOUR_MANAGER, status=ApprovalStatus.PENDING,
        )
        ApprovalService.review_membership(reviewer=self.superuser, membership_id=membership.id, approve=False)
        self.assertFalse(Conversation.objects.filter(team=self.team).exists())

    def test_removing_a_team_member_posts_a_removed_system_message(self):
        ApprovalService.review_membership(reviewer=self.superuser, membership_id=self.founder_membership.id, approve=True)
        recruit_membership = TeamMembership.objects.create(
            team=self.team, user=self.recruit, role=ArtistRole.TOUR_MANAGER, status=ApprovalStatus.PENDING,
        )
        ApprovalService.review_membership(reviewer=self.superuser, membership_id=recruit_membership.id, approve=True)

        TeamService.remove_member(actor=self.founder, team=self.team, membership_id=recruit_membership.id)

        conversation = Conversation.objects.get(team=self.team)
        system_message = Message.objects.filter(
            conversation=conversation, kind=Message.Kind.SYSTEM, system_event__event="member_removed_from_team",
        ).latest("created_at")
        self.assertEqual(system_message.system_event["actor"]["id"], self.recruit.pk)
        self.assertFalse(
            ConversationMember.objects.filter(conversation=conversation, user=self.recruit).exists()
        )
