from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class ClaimStatus(models.TextChoices):
    """Deliberately its own enum, not `apps.teams.models.ApprovalStatus` -
    this app is independent of teams (see `ArtistClaim` docstring), so it
    doesn't import from it.
    """

    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ArtistClaim(TimeStampedModel):
    """A user's claim to represent an artist - either an internal platform
    user (`accounts.User`, not `catalog.ArtistProfile`) or an external
    `seatgeek.Performers` row.

    Independent of team membership: claiming an artist here never creates or
    touches a `TeamMembership`, and adding someone to a team as the `artist`
    role never creates a claim here. This is a roster of "who says they
    represent this act", searchable on its own - many users may hold a claim
    (live or historical) on the same artist at once.
    """

    claimant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="artist_claims_made",
    )
    artist_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="artist_claims_received",
    )
    seatgeek_performer = models.ForeignKey(
        "seatgeek.Performers",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="claims",
    )

    # Same proof-of-representation shape as
    # apps.teams.models.ArtistRepresentationDetails - deliberately duplicated
    # rather than shared, since the two are unrelated features that happen to
    # ask for the same kind of proof.
    agency_roster_url = models.URLField(
        max_length=500,
        help_text="Link to the agency/management's public roster page listing this artist.",
    )
    confirmation_email = models.EmailField(
        help_text="Email address the artist confirmed representation from.",
    )
    company_agency = models.CharField(
        max_length=255, blank=True, help_text="Company or agency name of the claimant (optional).",
    )
    business_email = models.EmailField(help_text="Work/business email of the claimant.")
    adder_role = models.CharField(
        max_length=255, help_text="Claimant's role at their company (e.g. Booking Agent, Manager).",
    )
    representation = models.TextField(help_text="Free-text description of the representation arrangement.")
    note = models.TextField(blank=True)

    status = models.CharField(max_length=16, choices=ClaimStatus.choices, default=ClaimStatus.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="artist_claims_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        db_table = "artist_claims"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(artist_user__isnull=False, seatgeek_performer__isnull=True)
                    | models.Q(artist_user__isnull=True, seatgeek_performer__isnull=False)
                ),
                name="artist_claim_exactly_one_target",
            ),
            # One *live* claim per (claimant, target) - a rejected claim can
            # be resubmitted, so terminal rows are exempt (same pattern as
            # apps.teams.models.TeamInvitation's uniq_live_team_invitation).
            models.UniqueConstraint(
                fields=["claimant", "artist_user"],
                condition=models.Q(artist_user__isnull=False) & ~models.Q(status="rejected"),
                name="uniq_live_claimant_artist_user",
            ),
            models.UniqueConstraint(
                fields=["claimant", "seatgeek_performer"],
                condition=models.Q(seatgeek_performer__isnull=False) & ~models.Q(status="rejected"),
                name="uniq_live_claimant_sg_performer",
            ),
        ]
        indexes = [
            models.Index(fields=["artist_user", "status"]),
            models.Index(fields=["seatgeek_performer", "status"]),
            models.Index(fields=["claimant", "status"]),
        ]

    def __str__(self) -> str:
        target = f"artist user {self.artist_user_id}" if self.artist_user_id else f"sg performer {self.seatgeek_performer_id}"
        return f"claim by {self.claimant_id} on {target} ({self.status})"

    @property
    def target_type(self) -> str:
        return "internal" if self.artist_user_id else "seatgeek"

    @property
    def is_approved(self) -> bool:
        return self.status == ClaimStatus.APPROVED


class ArtistClaimDocument(TimeStampedModel):
    """An uploaded proof document attached to a claim (contract, ID, etc)."""

    claim = models.ForeignKey(ArtistClaim, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to="artist_claims/documents/")

    class Meta:
        db_table = "artist_claim_documents"

    def __str__(self) -> str:
        return f"document {self.pk} for claim {self.claim_id}"
