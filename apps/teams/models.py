from __future__ import annotations
import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.common.models import TimeStampedModel
from .roles import ROLE_CHOICES, TeamDomain, rank_of

INVITATION_TOKEN_BYTES = 32


class ApprovalStatus(models.TextChoices):
    """Superuser gate shared by teams and memberships.

    Nothing is active until a superuser approves it, so PENDING is the only
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


class TeamInvitation(TimeStampedModel):
    """An invite to hold `role` on `team`, addressed by email.

    The link is live as soon as it is created - the invitee can join right away.
    Joining does not make them an active member: acceptance creates a *pending*
    membership that a superuser still has to approve, exactly like a direct add.
    So the superuser gate lives on the resulting membership, not on the invite.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting Acceptance"
        ACCEPTED = "accepted", "Accepted"
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
