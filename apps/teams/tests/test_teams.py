import contextlib
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from apps.teams import roles as roles_module
from apps.teams.models import ApprovalStatus, Team, TeamInvitation, TeamMembership
from apps.teams.roles import (
    ROLE_RANKS,
    ArtistRole,
    TeamDomain,
    VenueRole,
    levels,
    outranks,
    rank_of,
    same_level,
)

User = get_user_model()


def make_user(email: str, role: str = "artist", **kwargs) -> User:
    return User.objects.create_user(email=email, name=email.split("@")[0], role=role, **kwargs)


class ApiTestCase(TestCase):
    """Base case that authenticates the way the API actually does.

    The project enables JWTAuthentication only - no SessionAuthentication - so
    `force_login` leaves `request.user` anonymous and every call 401s. Issue a
    real bearer token instead, matching apps/catalog/tests.
    """

    def login_as(self, user) -> None:
        token = RefreshToken.for_user(user).access_token
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"


class RoleHierarchyTests(TestCase):
    def test_rank_follows_declared_chain(self):
        self.assertEqual(rank_of(TeamDomain.ARTIST, ArtistRole.ARTIST), 0)
        self.assertEqual(rank_of(TeamDomain.ARTIST, ArtistRole.LEGAL_REPRESENTATIVE), 6)
        self.assertEqual(rank_of(TeamDomain.VENUE, VenueRole.CEO_GM), 0)
        self.assertEqual(rank_of(TeamDomain.VENUE, VenueRole.LEGAL_TEAM), 6)

    def test_role_from_other_domain_is_rejected(self):
        with self.assertRaises(KeyError):
            rank_of(TeamDomain.VENUE, ArtistRole.MANAGER)

    def test_outranks_is_strict(self):
        self.assertTrue(outranks(TeamDomain.ARTIST, ArtistRole.MANAGER, ArtistRole.TOUR_MANAGER))
        self.assertFalse(outranks(TeamDomain.ARTIST, ArtistRole.TOUR_MANAGER, ArtistRole.MANAGER))
        self.assertFalse(outranks(TeamDomain.ARTIST, ArtistRole.MANAGER, ArtistRole.MANAGER))


class SameLevelRoleTests(TestCase):
    """Two roles may share a rank; peers neither outrank nor report to another.

    No shipped role shares a level yet, so these patch a peer into the maps to
    prove the structure supports one. The patch is what adding a real peer to
    roles.py would look like - one enum entry (feeding labels) and one rank.
    """

    @contextlib.contextmanager
    def _with_peer(self):
        artist_ranks = dict(ROLE_RANKS[TeamDomain.ARTIST.value])
        artist_ranks["co_manager"] = artist_ranks[ArtistRole.MANAGER.value]  # rank 1
        with mock.patch.dict(
            ROLE_RANKS, {TeamDomain.ARTIST.value: artist_ranks}, clear=False
        ), mock.patch.dict(roles_module._ROLE_LABELS, {"co_manager": "Co-Manager"}):
            yield

    def test_peers_share_a_rank_and_neither_outranks(self):
        with self._with_peer():
            domain = TeamDomain.ARTIST
            self.assertEqual(rank_of(domain, "co_manager"), rank_of(domain, ArtistRole.MANAGER))
            self.assertTrue(same_level(domain, "co_manager", ArtistRole.MANAGER))
            self.assertFalse(outranks(domain, "co_manager", ArtistRole.MANAGER))
            self.assertFalse(outranks(domain, ArtistRole.MANAGER, "co_manager"))

    def test_peer_still_outranks_lower_levels(self):
        with self._with_peer():
            domain = TeamDomain.ARTIST
            self.assertTrue(outranks(domain, "co_manager", ArtistRole.TOUR_MANAGER))
            self.assertTrue(outranks(domain, ArtistRole.ARTIST, "co_manager"))

    def test_levels_groups_peers_into_one_entry(self):
        with self._with_peer():
            by_rank = {entry["rank"]: entry["roles"] for entry in levels(TeamDomain.ARTIST)}
            rank_1_roles = {row["role"] for row in by_rank[1]}
            self.assertEqual(rank_1_roles, {"manager", "co_manager"})
            self.assertEqual(len(by_rank[0]), 1)


class TeamCreateTests(ApiTestCase):
    def setUp(self):
        self.user = make_user("founder@example.com")
        self.login_as(self.user)

    def test_create_lands_auto_approved_with_pending_founder_membership(self):
        res = self.client.post(
            reverse("teams:team-list-create"),
            data={"domain": "artist", "name": "Team A", "role": "manager"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()["success"])

        team = Team.objects.get()
        self.assertEqual(team.status, ApprovalStatus.APPROVED)

        membership = TeamMembership.objects.get(team=team, user=self.user)
        self.assertEqual(membership.role, "manager")
        self.assertEqual(membership.status, ApprovalStatus.PENDING)

    def test_role_must_match_domain(self):
        res = self.client.post(
            reverse("teams:team-list-create"),
            data={"domain": "artist", "name": "Bad", "role": "ceo_gm"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "role_domain_mismatch")
        self.assertFalse(Team.objects.exists())


class TeamManageBeforeApprovalTests(ApiTestCase):
    def setUp(self):
        self.founder = make_user("founder@example.com")
        self.team = Team.objects.create(
            domain=TeamDomain.ARTIST, name="Team A", created_by=self.founder
        )
        self.membership = TeamMembership.objects.create(
            team=self.team, user=self.founder, role=ArtistRole.MANAGER
        )

    def test_cannot_manage_team_before_approval(self):
        other = make_user("other@example.com")
        self.login_as(self.founder)
        res = self.client.post(
            reverse("teams:member-list-create", args=[self.team.id]),
            data={"user_id": other.id, "role": "tour_manager"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "team_not_approved")


class MembershipTests(ApiTestCase):
    def setUp(self):
        self.founder = make_user("founder@example.com")
        self.other = make_user("other@example.com")
        self.superuser = make_user("root@example.com", is_superuser=True, is_staff=True)
        self.team = Team.objects.create(
            domain=TeamDomain.ARTIST,
            name="Team A",
            created_by=self.founder,
            status=ApprovalStatus.APPROVED,
        )
        TeamMembership.objects.create(
            team=self.team,
            user=self.founder,
            role=ArtistRole.MANAGER,
            status=ApprovalStatus.APPROVED,
        )

    def test_added_member_is_pending_until_reviewed(self):
        self.login_as(self.founder)
        res = self.client.post(
            reverse("teams:member-list-create", args=[self.team.id]),
            data={"user_id": self.other.id, "role": "tour_manager"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        membership = TeamMembership.objects.get(user=self.other)
        self.assertEqual(membership.status, ApprovalStatus.PENDING)

    def test_one_role_per_team_second_role_rejected(self):
        self.login_as(self.founder)
        url = reverse("teams:member-list-create", args=[self.team.id])
        self.client.post(
            url,
            data={"user_id": self.other.id, "role": "tour_manager"},
            content_type="application/json",
        )
        # A different role for the same user in the same team must conflict.
        res = self.client.post(
            url,
            data={"user_id": self.other.id, "role": "business_manager"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "duplicate_membership")
        self.assertEqual(TeamMembership.objects.filter(user=self.other).count(), 1)

    def test_same_user_may_hold_a_role_in_a_different_team(self):
        team_b = Team.objects.create(
            domain=TeamDomain.ARTIST, name="Team B", created_by=self.founder,
            status=ApprovalStatus.APPROVED,
        )
        TeamMembership.objects.create(
            team=self.team, user=self.other, role=ArtistRole.TOUR_MANAGER,
            status=ApprovalStatus.APPROVED,
        )
        TeamMembership.objects.create(
            team=team_b, user=self.other, role=ArtistRole.BUSINESS_MANAGER,
            status=ApprovalStatus.APPROVED,
        )
        self.assertEqual(TeamMembership.objects.filter(user=self.other).count(), 2)

    def test_same_role_twice_is_rejected(self):
        self.login_as(self.founder)
        url = reverse("teams:member-list-create", args=[self.team.id])
        payload = {"user_id": self.other.id, "role": "tour_manager"}
        self.client.post(url, data=payload, content_type="application/json")
        res = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "duplicate_membership")

    def test_effective_rank_returns_the_single_role(self):
        from apps.teams.services import TeamService

        TeamMembership.objects.create(
            team=self.team, user=self.other, role=ArtistRole.TOUR_MANAGER,  # rank 5
            status=ApprovalStatus.APPROVED,
        )
        self.assertEqual(TeamService.effective_rank(self.team, self.other), 5)
        # A non-member has no rank.
        self.assertIsNone(
            TeamService.effective_rank(self.team, make_user("nobody@example.com"))
        )

    def test_non_member_cannot_view_team(self):
        stranger = make_user("stranger@example.com")
        self.login_as(stranger)
        res = self.client.get(reverse("teams:team-detail", args=[self.team.id]))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "not_team_member")


class InvitationTests(ApiTestCase):
    def setUp(self):
        self.founder = make_user("founder@example.com")
        self.invitee = make_user("invitee@example.com")
        self.superuser = make_user("root@example.com", is_superuser=True, is_staff=True)
        self.team = Team.objects.create(
            domain=TeamDomain.ARTIST,
            name="Team A",
            created_by=self.founder,
            status=ApprovalStatus.APPROVED,
        )
        TeamMembership.objects.create(
            team=self.team, user=self.founder, role=ArtistRole.MANAGER,
            status=ApprovalStatus.APPROVED,
        )

    def _invite(self, email="invitee@example.com", role="tour_manager"):
        self.login_as(self.founder)
        res = self.client.post(
            reverse("teams:invitation-list-create", args=[self.team.id]),
            data={"email": email, "role": role},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        return TeamInvitation.objects.get(email=email, role=role)

    def test_invitation_link_is_live_immediately(self):
        # No superuser step: the link works the moment it is created.
        invitation = self._invite()
        self.assertEqual(invitation.status, TeamInvitation.Status.PENDING)
        self.assertTrue(invitation.is_acceptable)

    def test_creating_invitation_emails_the_invitee(self):
        from django.core import mail

        self.assertEqual(len(mail.outbox), 0)
        invitation = self._invite(email="newperson@example.com")

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["newperson@example.com"])
        self.assertIn(invitation.token, message.body)
        self.assertIn("Team A", message.subject)

    def test_accepting_creates_a_pending_membership(self):
        invitation = self._invite()

        self.login_as(self.invitee)
        res = self.client.post(
            reverse("teams:invitation-accept"),
            data={"token": invitation.token},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        membership = TeamMembership.objects.get(user=self.invitee, team=self.team)
        self.assertEqual(membership.status, ApprovalStatus.PENDING)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, TeamInvitation.Status.ACCEPTED)
        self.assertEqual(invitation.accepted_by, self.invitee)

    def test_superuser_approves_the_joined_membership(self):
        invitation = self._invite()
        self.login_as(self.invitee)
        self.client.post(
            reverse("teams:invitation-accept"),
            data={"token": invitation.token},
            content_type="application/json",
        )
        membership = TeamMembership.objects.get(user=self.invitee)

        # It shows up in the superuser membership queue and can be approved.
        self.login_as(self.superuser)
        res = self.client.post(
            reverse("teams:review-membership", args=[membership.id]),
            data={"approve": True},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.status, ApprovalStatus.APPROVED)

    def test_accepting_a_revoked_invitation_fails(self):
        invitation = self._invite()
        self.login_as(self.founder)
        self.client.post(
            reverse("teams:invitation-revoke", args=[self.team.id, invitation.id]),
            content_type="application/json",
        )

        self.login_as(self.invitee)
        res = self.client.post(
            reverse("teams:invitation-accept"),
            data={"token": invitation.token},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invitation_not_acceptable")
        self.assertFalse(TeamMembership.objects.filter(user=self.invitee).exists())

    def test_wrong_user_cannot_redeem_someone_elses_token(self):
        invitation = self._invite()

        thief = make_user("thief@example.com")
        self.login_as(thief)
        res = self.client.post(
            reverse("teams:invitation-accept"),
            data={"token": invitation.token},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "invitation_email_mismatch")

    def test_accepting_invite_conflicts_with_existing_role(self):
        # Invitee is already in the team as Segment Agent.
        TeamMembership.objects.create(
            team=self.team, user=self.invitee, role=ArtistRole.SEGMENT_AGENT,
            status=ApprovalStatus.APPROVED,
        )
        invitation = self._invite(role="tour_manager")

        self.login_as(self.invitee)
        res = self.client.post(
            reverse("teams:invitation-accept"),
            data={"token": invitation.token},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "duplicate_membership")
        # Their original role is untouched.
        self.assertEqual(TeamMembership.objects.get(user=self.invitee).role, "segment_agent")

    def test_duplicate_live_invitation_is_rejected(self):
        self._invite()
        self.login_as(self.founder)
        res = self.client.post(
            reverse("teams:invitation-list-create", args=[self.team.id]),
            data={"email": "invitee@example.com", "role": "tour_manager"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "duplicate_invitation")

    def test_revoked_invitation_can_be_reissued(self):
        invitation = self._invite()
        self.login_as(self.founder)
        res = self.client.post(
            reverse("teams:invitation-revoke", args=[self.team.id, invitation.id]),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        res = self.client.post(
            reverse("teams:invitation-list-create", args=[self.team.id]),
            data={"email": "invitee@example.com", "role": "tour_manager"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)


class ReferralAutoEnrollTests(TestCase):
    """A user invited by email before signing up is enrolled on verification.

    on_commit callbacks do not fire inside TestCase's outer transaction unless
    captured, so every path that verifies an email is wrapped in
    captureOnCommitCallbacks(execute=True).
    """

    def setUp(self):
        self.founder = make_user("founder@example.com")
        self.superuser = make_user("root@example.com", is_superuser=True, is_staff=True)
        self.team = Team.objects.create(
            domain=TeamDomain.ARTIST,
            name="Team A",
            created_by=self.founder,
            status=ApprovalStatus.APPROVED,
        )
        TeamMembership.objects.create(
            team=self.team, user=self.founder, role=ArtistRole.MANAGER,
            status=ApprovalStatus.APPROVED,
        )

    def _live_invite(self, email, role="tour_manager", team=None):
        from apps.teams.services import InvitationService

        return InvitationService.create(
            actor=self.founder, team=team or self.team, email=email, role=role
        )

    def test_verifying_email_claims_a_live_invite_as_pending(self):
        invite = self._live_invite("newbie@example.com")

        # New user signs up (unverified) - nothing claimed yet.
        newbie = make_user("newbie@example.com")
        newbie.email_verified_at = None
        newbie.save(update_fields=["email_verified_at"])
        self.assertFalse(TeamMembership.objects.filter(user=newbie).exists())

        # Verification fires the signal.
        with self.captureOnCommitCallbacks(execute=True):
            newbie.mark_email_verified()

        membership = TeamMembership.objects.get(user=newbie, team=self.team)
        # Auto-enrolled, but still awaiting superuser approval - not active yet.
        self.assertEqual(membership.status, ApprovalStatus.PENDING)
        self.assertEqual(membership.role, "tour_manager")
        invite.refresh_from_db()
        self.assertEqual(invite.status, TeamInvitation.Status.ACCEPTED)

    def test_revoked_invite_is_not_auto_claimed(self):
        from apps.teams.services import InvitationService

        invite = self._live_invite("newbie@example.com")
        InvitationService.revoke(
            actor=self.founder, team=self.team, invitation_id=invite.id
        )

        newbie = make_user("newbie@example.com", email_verified_at=None)
        with self.captureOnCommitCallbacks(execute=True):
            newbie.mark_email_verified()

        self.assertFalse(TeamMembership.objects.filter(user=newbie).exists())

    def test_multiple_live_invites_all_claimed(self):
        team_b = Team.objects.create(
            domain=TeamDomain.VENUE, name="Venue B", created_by=self.founder,
            status=ApprovalStatus.APPROVED,
        )
        TeamMembership.objects.create(
            team=team_b, user=self.founder, role=VenueRole.CEO_GM,
            status=ApprovalStatus.APPROVED,
        )
        self._live_invite("newbie@example.com", role="tour_manager")
        self._live_invite("newbie@example.com", role="talent_buyer", team=team_b)

        newbie = make_user("newbie@example.com", email_verified_at=None)
        with self.captureOnCommitCallbacks(execute=True):
            newbie.mark_email_verified()

        self.assertEqual(TeamMembership.objects.filter(user=newbie).count(), 2)

    def test_already_verified_profile_save_does_not_rescan(self):
        # A live invite exists, but this user was invited under a different
        # address. A later profile save must not sweep it up.
        self._live_invite("someone-else@example.com")

        user = make_user("verified@example.com")  # created already verified
        with self.captureOnCommitCallbacks(execute=True):
            user.name = "Renamed"
            user.save(update_fields=["name", "updated_at"])

        self.assertFalse(TeamMembership.objects.filter(user=user).exists())
