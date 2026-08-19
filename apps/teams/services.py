from __future__ import annotations
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from . import exceptions as exc
from .emails import send_invitation_email
from .models import (
    ApprovalStatus,
    ArtistRepresentationDetails,
    MembershipDocument,
    Team,
    TeamInvitation,
    TeamMembership,
)
from .notifications import notify_invitation_received
from .roles import ArtistRole, is_valid_role, rank_of

User = get_user_model()

DEFAULT_INVITATION_TTL_DAYS = 7


def _invitation_ttl() -> timedelta:
    days = getattr(settings, "TEAM_INVITATION_TTL_DAYS", DEFAULT_INVITATION_TTL_DAYS)
    return timedelta(days=days)


class TeamService:
    """Team lifecycle and membership.

    Authorisation model: any approved member of a team may invite or add
    people. That is intentionally permissive because an admin approves every
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
    def list_for(user, search: str | None = None) -> QuerySet[Team]:
        """Approved teams the user belongs to, plus their own pending teams.

        The founder keeps sight of a team while it is under review; everyone
        else only sees teams that are live.

        `search` filters by team name (case-insensitive, substring).
        """
        member_of = Q(
            status=ApprovalStatus.APPROVED,
            memberships__user=user,
            memberships__status=ApprovalStatus.APPROVED,
        )
        founded_by_user = Q(created_by=user)
        qs = (
            Team.objects.filter(member_of | founded_by_user)
            .select_related("created_by")
            .distinct()
            .order_by("-created_at")
        )
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @staticmethod
    def search_related_users(user, email: str | None = None) -> QuerySet[User]:
        """Users who share at least one approved team with `user` - i.e. teammates
        across every team `user` belongs to, regardless of which team. Excludes
        `user` themselves. `email` filters case-insensitively, substring.
        """
        my_team_ids = TeamMembership.objects.filter(
            user=user, status=ApprovalStatus.APPROVED
        ).values_list("team_id", flat=True)
        qs = (
            User.objects.filter(
                team_memberships__team_id__in=my_team_ids,
                team_memberships__status=ApprovalStatus.APPROVED,
                is_active=True,
            )
            .exclude(pk=user.pk)
            .distinct()
            .order_by("name")
        )
        if email:
            qs = qs.filter(email__icontains=email)
        return qs

    @staticmethod
    def search_all_users(email: str | None = None) -> QuerySet[User]:
        """Platform-wide user search - not scoped to any shared team."""
        qs = User.objects.filter(is_active=True).order_by("name")
        if email:
            qs = qs.filter(email__icontains=email)
        return qs

    @staticmethod
    def search_public_teams(search: str | None = None) -> QuerySet[Team]:
        """Platform-wide team search - not scoped to membership. Approved teams
        only: a team still under admin review isn't public yet.
        """
        qs = Team.objects.filter(status=ApprovalStatus.APPROVED).select_related("created_by").order_by("name")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

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
    def delete(*, actor, team: Team) -> None:
        """Delete a team. Only the user who created it may do this."""
        if team.created_by_id != actor.id:
            raise exc.NotTeamCreator()
        team.delete()

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
    def list_members(team: Team, search: str | None = None) -> QuerySet[TeamMembership]:
        """Members of `team`. `search` filters by member name or email
        (case-insensitive, substring)."""
        qs = (
            TeamMembership.objects.filter(team=team)
            .select_related("user", "team")
            .order_by("role", "user__name")
        )
        if search:
            qs = qs.filter(Q(user__name__icontains=search) | Q(user__email__icontains=search))
        return qs

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
    def add_member(
        *,
        actor,
        team: Team,
        user_id: int,
        role: str,
        agency_roster_url: str | None = None,
        confirmation_email: str | None = None,
        company_agency: str = "",
        business_email: str | None = None,
        adder_role: str | None = None,
        representation: str | None = None,
        note: str = "",
        documents=None,
    ) -> TeamMembership:
        """Add an existing platform user directly. Lands PENDING for review.

        `agency_roster_url` / `confirmation_email` / `company_agency` /
        `business_email` / `adder_role` / `representation` / `note` / `documents`
        only apply to the base `artist` role (roles.ArtistRole.ARTIST) - proof
        that the caller represents them. The serializer only requires them for
        that role; here they just get attached to an `ArtistRepresentationDetails`
        row when present, so every other role's add flow is untouched.
        """
        TeamService.assert_can_manage(actor, team)
        TeamService._assert_role_matches_domain(team.domain, role)

        try:
            target = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            raise exc.MembershipNotFound(detail="No active user with that id.")

        try:
            with transaction.atomic():
                membership = TeamMembership.objects.create(
                    team=team,
                    user=target,
                    role=role,
                    status=ApprovalStatus.PENDING,
                    invited_by=actor,
                )
                if role == ArtistRole.ARTIST.value:
                    details = ArtistRepresentationDetails.objects.create(
                        membership=membership,
                        agency_roster_url=agency_roster_url,
                        confirmation_email=confirmation_email,
                        company_agency=company_agency,
                        business_email=business_email,
                        adder_role=adder_role,
                        representation=representation,
                        note=note,
                    )
                for upload in documents or []:
                    MembershipDocument.objects.create(membership=membership, file=upload)
        except IntegrityError:
            # uniq_team_user - the user is already in this team in some role.
            raise exc.DuplicateMembership()
        return membership

    @staticmethod
    def remove_member(*, actor, team: Team, membership_id: int) -> None:
        TeamService.assert_can_manage(actor, team)
        deleted, _ = TeamMembership.objects.filter(pk=membership_id, team=team).delete()
        if not deleted:
            raise exc.MembershipNotFound()


class InvitationService:
    @staticmethod
    def create(
        *,
        actor,
        team: Team,
        email: str,
        role: str,
        agency_roster_url: str | None = None,
        confirmation_email: str | None = None,
        company_agency: str = "",
        business_email: str | None = None,
        adder_role: str | None = None,
        representation: str | None = None,
        note: str = "",
        documents=None,
    ) -> TeamInvitation:
        """Issue an invitation and email it. Live immediately; acceptance yields
        a pending member.

        The email is sent after the row commits, same ordering as the OTP flow
        (apps.accounts.services.OTPService.issue_and_send) - a mail-server
        failure surfaces as a real error to the caller, but never rolls back an
        invitation that was otherwise valid to create.

        Same `artist`-only extra fields as `TeamService.add_member`. There is
        no membership row yet to attach `ArtistRepresentationDetails` to, so
        it's parented to this invitation instead - `_materialize` re-points it
        at the real membership once accepted.
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
                if role == ArtistRole.ARTIST.value:
                    details = ArtistRepresentationDetails.objects.create(
                        invitation=invitation,
                        agency_roster_url=agency_roster_url,
                        confirmation_email=confirmation_email,
                        company_agency=company_agency,
                        business_email=business_email,
                        adder_role=adder_role,
                        representation=representation,
                        note=note,
                    )
                for upload in documents or []:
                    MembershipDocument.objects.create(invitation=invitation, file=upload)
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

        # Re-parent any documents staged on the invitation.
        invitation.documents.update(invitation=None, membership=membership)

        # Artist invites stage agency_roster_url/confirmation_email
        # on the invitation (see InvitationService.create) since there's no
        # membership row until now. Re-point that row at the real membership.
        details = getattr(invitation, "artist_representation_details", None)
        if details is not None and not hasattr(membership, "artist_representation_details"):
            details.invitation = None
            details.membership = membership
            details.save(update_fields=["invitation", "membership", "updated_at"])

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
    @transaction.atomic
    def decline(*, user, token: str) -> TeamInvitation:
        """Invitee-initiated decline. Distinct from `revoke`, which is the
        team side withdrawing the invite - this is the recipient saying no.
        """
        try:
            invitation = TeamInvitation.objects.select_for_update().get(token=token)
        except TeamInvitation.DoesNotExist:
            raise exc.InvitationNotFound()

        if invitation.status != TeamInvitation.Status.PENDING:
            raise exc.InvitationNotAcceptable()
        if invitation.is_expired:
            raise exc.InvitationExpired()
        if invitation.email.lower() != user.email.lower():
            raise exc.InvitationEmailMismatch()

        invitation.status = TeamInvitation.Status.DECLINED
        invitation.save(update_fields=["status", "updated_at"])
        return invitation

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
    """The admin review gate.

    Nothing here checks permissions - the view enforces `IsAdmin`. Keeping
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
