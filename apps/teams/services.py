from __future__ import annotations
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from . import exceptions as exc
from .emails import send_invitation_email
from .models import ApprovalStatus, Team, TeamInvitation, TeamMembership
from .notifications import notify_invitation_received
from .roles import is_valid_role, rank_of

User = get_user_model()

DEFAULT_INVITATION_TTL_DAYS = 7


def _invitation_ttl() -> timedelta:
    days = getattr(settings, "TEAM_INVITATION_TTL_DAYS", DEFAULT_INVITATION_TTL_DAYS)
    return timedelta(days=days)


class TeamService:
    """Team lifecycle and membership.

    Authorisation model: any approved member of a team may invite or add
    people. That is intentionally permissive because a superuser approves every
    team, every role assignment, and every invitation before it takes effect -
    the review gate is the control, not the caller's rank.
    """

    @staticmethod
    def _assert_role_matches_domain(domain: str, role: str) -> None:
        if not is_valid_role(domain, role):
            raise exc.RoleDomainMismatch()

    @staticmethod
    @transaction.atomic
    def create(*, user, domain: str, name: str, role: str) -> Team:
        """Create a team (auto-approved) plus the founder's own membership (PENDING).

        The team itself needs no superuser review - only membership does, same
        as adding anyone else to a team. Both rows are written in one
        transaction: a team whose founder has no membership row would be
        unreachable if the second write failed.
        """
        TeamService._assert_role_matches_domain(domain, role)

        team = Team.objects.create(
            domain=domain,
            name=name,
            created_by=user,
            status=ApprovalStatus.APPROVED,
            approved_at=timezone.now(),
        )
        TeamMembership.objects.create(
            team=team,
            user=user,
            role=role,
            status=ApprovalStatus.PENDING,
        )
        return team

    @staticmethod
    def list_for(user) -> QuerySet[Team]:
        """Approved teams the user belongs to, plus their own pending teams.

        The founder keeps sight of a team while it is under review; everyone
        else only sees teams that are live.
        """
        member_of = Q(
            status=ApprovalStatus.APPROVED,
            memberships__user=user,
            memberships__status=ApprovalStatus.APPROVED,
        )
        founded_by_user = Q(created_by=user)
        return (
            Team.objects.filter(member_of | founded_by_user)
            .select_related("created_by")
            .distinct()
            .order_by("-created_at")
        )

    @staticmethod
    def get_for_member(user, team_id: int) -> Team:
        """Fetch a team the user may view, or raise.

        Splits "no such team" from "not your team" deliberately: both return a
        distinct `error.code` so the frontend can tell a dead link from a
        permission problem.
        """
        try:
            team = Team.objects.select_related("created_by").get(pk=team_id)
        except Team.DoesNotExist:
            raise exc.TeamNotFound()

        if team.created_by_id == user.id:
            return team

        is_member = TeamMembership.objects.filter(
            team=team, user=user, status=ApprovalStatus.APPROVED
        ).exists()
        if not is_member:
            raise exc.NotTeamMember()
        return team

    @staticmethod
    def assert_can_manage(user, team: Team) -> None:
        """Guard for mutations: team must be live and the actor an approved member."""
        if not team.is_approved:
            raise exc.TeamNotApproved()
        is_member = TeamMembership.objects.filter(
            team=team, user=user, status=ApprovalStatus.APPROVED
        ).exists()
        if not is_member:
            raise exc.NotTeamMember()

    @staticmethod
    def list_members(team: Team) -> QuerySet[TeamMembership]:
        return (
            TeamMembership.objects.filter(team=team)
            .select_related("user", "team")
            .order_by("role", "user__name")
        )

    @staticmethod
    def member_counts(team: Team) -> dict[str, int]:
        rows = (
            TeamMembership.objects.filter(team=team)
            .values("status")
            .annotate(count=Count("id"))
        )
        by_status = {row["status"]: row["count"] for row in rows}
        active = by_status.get(ApprovalStatus.APPROVED, 0)
        pending = by_status.get(ApprovalStatus.PENDING, 0)
        declined = by_status.get(ApprovalStatus.REJECTED, 0)
        return {
            "total": active + pending + declined,
            "active": active,
            "pending": pending,
            "declined": declined,
        }

    @staticmethod
    def effective_rank(team: Team, user) -> int | None:
        """Rank of the user's role on the team, or None if not an approved member.

        One role per team, so this is unambiguous - the single approved
        membership's rank.
        """
        membership = (
            TeamMembership.objects.filter(
                team=team, user=user, status=ApprovalStatus.APPROVED
            )
            .only("role")
            .first()
        )
        return rank_of(team.domain, membership.role) if membership else None

    @staticmethod
    def add_member(*, actor, team: Team, user_id: int, role: str) -> TeamMembership:
        """Add an existing platform user directly. Lands PENDING for review."""
        TeamService.assert_can_manage(actor, team)
        TeamService._assert_role_matches_domain(team.domain, role)

        try:
            target = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            raise exc.MembershipNotFound(detail="No active user with that id.")

        try:
            with transaction.atomic():
                return TeamMembership.objects.create(
                    team=team,
                    user=target,
                    role=role,
                    status=ApprovalStatus.PENDING,
                    invited_by=actor,
                )
        except IntegrityError:
            # uniq_team_user - the user is already in this team in some role.
            raise exc.DuplicateMembership()

    @staticmethod
    def remove_member(*, actor, team: Team, membership_id: int) -> None:
        TeamService.assert_can_manage(actor, team)
        deleted, _ = TeamMembership.objects.filter(pk=membership_id, team=team).delete()
        if not deleted:
            raise exc.MembershipNotFound()


class InvitationService:
    @staticmethod
    def create(*, actor, team: Team, email: str, role: str) -> TeamInvitation:
        """Issue an invitation and email it. Live immediately; acceptance yields
        a pending member.

        The email is sent after the row commits, same ordering as the OTP flow
        (apps.accounts.services.OTPService.issue_and_send) - a mail-server
        failure surfaces as a real error to the caller, but never rolls back an
        invitation that was otherwise valid to create.
        """
        TeamService.assert_can_manage(actor, team)
        TeamService._assert_role_matches_domain(team.domain, role)

        try:
            with transaction.atomic():
                invitation = TeamInvitation.objects.create(
                    team=team,
                    email=email.lower().strip(),
                    role=role,
                    token=TeamInvitation.new_token(),
                    invited_by=actor,
                    status=TeamInvitation.Status.PENDING,
                    expires_at=timezone.now() + _invitation_ttl(),
                )
        except IntegrityError:
            # uniq_live_team_invitation
            raise exc.DuplicateInvitation()

        send_invitation_email(invitation=invitation)
        notify_invitation_received(invitation=invitation)

        return invitation

    @staticmethod
    def list_for_team(team: Team) -> QuerySet[TeamInvitation]:
        return (
            TeamInvitation.objects.filter(team=team)
            .select_related("invited_by", "team")
            .order_by("-created_at")
        )

    @staticmethod
    def _materialize(*, invitation: TeamInvitation, user) -> TeamMembership:
        """Turn a live invite into a *pending* membership.

        Assumes `invitation` is already row-locked by the caller. Shared by the
        token path (an existing user clicking the link) and the email path
        (a new user auto-enrolled after signup) so both enforce the same gates:
        awaiting acceptance, unexpired, and addressed to this user.

        The membership lands PENDING - joining does not activate anyone. A
        superuser approves it afterwards, the same review a direct add gets.
        """
        if invitation.status != TeamInvitation.Status.PENDING:
            raise exc.InvitationNotAcceptable()
        if invitation.is_expired:
            raise exc.InvitationExpired()
        if invitation.email.lower() != user.email.lower():
            raise exc.InvitationEmailMismatch()

        # One role per team. Already in this team as a different role -> the
        # invite conflicts. Same role -> idempotent, return what they have.
        existing = (
            TeamMembership.objects.filter(team=invitation.team, user=user)
            .select_for_update()
            .first()
        )
        if existing is not None:
            if existing.role != invitation.role:
                raise exc.DuplicateMembership()
            membership = existing
        else:
            membership = TeamMembership.objects.create(
                team=invitation.team,
                user=user,
                role=invitation.role,
                status=ApprovalStatus.PENDING,
                invited_by=invitation.invited_by,
            )

        invitation.status = TeamInvitation.Status.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.accepted_by = user
        invitation.save(update_fields=["status", "accepted_at", "accepted_by", "updated_at"])
        return membership

    @staticmethod
    @transaction.atomic
    def accept(*, user, token: str) -> TeamMembership:
        """Redeem a live invite by its token (existing-user path)."""
        try:
            invitation = TeamInvitation.objects.select_for_update().get(token=token)
        except TeamInvitation.DoesNotExist:
            raise exc.InvitationNotFound()
        return InvitationService._materialize(invitation=invitation, user=user)

    @staticmethod
    def claim_all_for_user(user) -> list[TeamMembership]:
        """Auto-enroll a freshly verified user into every invite awaiting them.

        The referral path: someone was invited by email before having an
        account, signed up through the normal flow, and just verified that
        email. Their OTP proves control of the invited address, so live invites
        for it are redeemed without a token - each yielding a pending membership
        that a superuser still approves.

        Best-effort and side-effect-only - never raises. A single bad invite
        (expired, or racing another claim) is skipped, not allowed to break the
        signup that triggered this. Each invite is claimed in its own
        transaction so one failure cannot roll back the others.
        """
        if not user.is_email_verified:
            return []

        invitation_ids = list(
            TeamInvitation.objects.filter(
                email__iexact=user.email,
                status=TeamInvitation.Status.PENDING,
            ).values_list("id", flat=True)
        )

        claimed: list[TeamMembership] = []
        for invitation_id in invitation_ids:
            try:
                with transaction.atomic():
                    invitation = TeamInvitation.objects.select_for_update().get(pk=invitation_id)
                    claimed.append(
                        InvitationService._materialize(invitation=invitation, user=user)
                    )
            except (
                exc.InvitationNotAcceptable,
                exc.InvitationExpired,
                exc.InvitationEmailMismatch,
                exc.DuplicateMembership,
                TeamInvitation.DoesNotExist,
            ):
                # Raced, expired, not for this user, or conflicts with a role
                # they already hold in that team - skip it.
                continue
        return claimed

    @staticmethod
    def revoke(*, actor, team: Team, invitation_id: int) -> TeamInvitation:
        TeamService.assert_can_manage(actor, team)
        try:
            invitation = TeamInvitation.objects.get(pk=invitation_id, team=team)
        except TeamInvitation.DoesNotExist:
            raise exc.InvitationNotFound()

        if invitation.status == TeamInvitation.Status.ACCEPTED:
            raise exc.InvitationNotAcceptable(detail="Already accepted.")

        invitation.status = TeamInvitation.Status.REVOKED
        invitation.save(update_fields=["status", "updated_at"])
        return invitation


class ApprovalService:
    """The superuser review gate.

    Nothing here checks permissions - the view enforces `IsSuperUser`. Keeping
    the check at the edge means these methods stay usable from a management
    command or the admin without a fake request user.
    """

    @staticmethod
    def list_memberships(status: str | None = None) -> QuerySet[TeamMembership]:
        """Review queue. Defaults to the pending queue; pass an
        ApprovalStatus value to browse approved/rejected history instead.
        """
        qs = TeamMembership.objects.select_related("user", "team", "invited_by", "approved_by")
        qs = qs.filter(status=status if status else ApprovalStatus.PENDING)
        return qs.order_by("created_at")

    @staticmethod
    def get_membership(membership_id: int) -> TeamMembership:
        try:
            return TeamMembership.objects.select_related(
                "user", "team", "invited_by", "approved_by"
            ).get(pk=membership_id)
        except TeamMembership.DoesNotExist:
            raise exc.MembershipNotFound()

    @staticmethod
    @transaction.atomic
    def review_membership(
        *, reviewer, membership_id: int, approve: bool, note: str = ""
    ) -> TeamMembership:
        try:
            membership = TeamMembership.objects.select_for_update().get(pk=membership_id)
        except TeamMembership.DoesNotExist:
            raise exc.MembershipNotFound()

        if membership.status != ApprovalStatus.PENDING:
            raise exc.AlreadyReviewed()

        now = timezone.now()
        membership.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
        membership.approved_by = reviewer
        membership.approved_at = now if approve else None
        membership.review_note = note
        membership.save(
            update_fields=["status", "approved_by", "approved_at", "review_note", "updated_at"]
        )
        return membership
