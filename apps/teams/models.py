from __future__ import annotations
import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.common.models import TimeStampedModel
from .roles import ROLE_CHOICES, TeamDomain, rank_of

INVITATION_TOKEN_BYTES = 32


class ApprovalStatus(models.TextChoices):
    """Admin gate shared by teams and memberships.

    Nothing is active until an admin approves it, so PENDING is the only
    sensible default and every query that powers real behaviour must filter on
    APPROVED explicitly.
    """

    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Team(TimeStampedModel):
    domain = models.CharField(max_length=16, choices=TeamDomain.choices)
    name = models.CharField(max_length=255)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_teams",
    )

    status = models.CharField(
        max_length=16,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_teams",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        db_table = "teams"
        indexes = [
            models.Index(fields=["domain", "status"]),
            models.Index(fields=["created_by", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.domain})"

    @property
    def is_approved(self) -> bool:
        return self.status == ApprovalStatus.APPROVED


class TeamMembership(TimeStampedModel):
    """A user's single role in a team.

    One role per user per team: uniqueness is on (team, user). A user still
    holds different roles across different teams - the constraint is per team,
    not global.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships",
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES)

    status = models.CharField(
        max_length=16,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_memberships_invited",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_memberships_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        db_table = "team_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["team", "user"],
                name="uniq_team_user",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "status"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} as {self.role} in team {self.team_id}"

    @property
    def rank(self) -> int:
        return rank_of(self.team.domain, self.role)

    @property
    def is_approved(self) -> bool:
        return self.status == ApprovalStatus.APPROVED


class ArtistRepresentationDetails(TimeStampedModel):

    membership = models.OneToOneField(
        TeamMembership,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="artist_representation_details",
    )
    invitation = models.OneToOneField(
        "TeamInvitation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="artist_representation_details",
    )
    agency_roster_url = models.URLField(
        max_length=500,
        help_text="Link to the agency/management's public roster page listing this artist.",
    )
    confirmation_email = models.EmailField(
        help_text="Email address the artist confirmed representation from.",
    )

    # Details about the person submitting the representation claim.
    company_agency = models.CharField(
        max_length=255,
        blank=True,
        help_text="Company or agency name of the person adding the artist (optional).",
    )
    business_email = models.EmailField(
        help_text="Work/business email of the person adding the artist.",
    )
    adder_role = models.CharField(
        max_length=255,
        help_text="Role of the person adding the artist at their company (e.g. Booking Agent, Manager).",
    )
    representation = models.TextField(
        help_text="Free-text description of the representation arrangement.",
    )

    note = models.TextField(blank=True)

    class Meta:
        db_table = "team_artist_representation_details"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(membership__isnull=False, invitation__isnull=True)
                    | models.Q(membership__isnull=True, invitation__isnull=False)
                ),
                name="artist_repr_details_exactly_one_parent",
            ),
        ]

    def __str__(self) -> str:
        parent = f"membership {self.membership_id}" if self.membership_id else f"invitation {self.invitation_id}"
        return f"representation details for {parent}"


class ArtistRepresentationDocument(TimeStampedModel):
    """One uploaded proof-of-representation file. Many per `details` row - a
    manager may attach a contract, an ID, an agency letter, etc.
    """

    details = models.ForeignKey(
        ArtistRepresentationDetails,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to="teams/artist_representation/")

    class Meta:
        db_table = "team_artist_representation_documents"

    def __str__(self) -> str:
        return f"document {self.pk}"


class TeamInvitation(TimeStampedModel):
    """An invite to hold `role` on `team`, addressed by email.

    The link is live as soon as it is created - the invitee can join right away.
    Joining does not make them an active member: acceptance creates a *pending*
    membership that an admin still has to approve, exactly like a direct add.
    So the admin gate lives on the resulting membership, not on the invite.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting Acceptance"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        REVOKED = "revoked", "Revoked"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=32, choices=ROLE_CHOICES)
    token = models.CharField(max_length=64, unique=True)

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_invitations_sent",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )

    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_invitations_accepted",
    )

    class Meta:
        db_table = "team_invitations"
        constraints = [
            # One live (awaiting-acceptance) invite per (team, email, role).
            # Terminal rows are exempt so a revoked invite can be reissued.
            models.UniqueConstraint(
                fields=["team", "email", "role"],
                condition=models.Q(status="pending"),
                name="uniq_live_team_invitation",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "status"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self) -> str:
        return f"invite {self.email} as {self.role} to team {self.team_id}"

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(INVITATION_TOKEN_BYTES)[:64]

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_acceptable(self) -> bool:
        return self.status == self.Status.PENDING and not self.is_expired
