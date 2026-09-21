from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.seatgeek.models import Performers

from . import exceptions as exc
from .models import ArtistClaim, ArtistClaimDocument, ClaimStatus

User = get_user_model()


class ArtistClaimService:
    @staticmethod
    @transaction.atomic
    def create(
        *,
        claimant: User,
        artist_user_id: int | None = None,
        seatgeek_performer_id: str | None = None,
        agency_roster_url: str,
        confirmation_email: str,
        business_email: str,
        adder_role: str,
        representation: str,
        company_agency: str = "",
        note: str = "",
        documents=None,
    ) -> ArtistClaim:
        """File a claim on exactly one target - an internal platform user or
        a SeatGeek performer, never both. Lands PENDING; a superadmin reviews
        it separately (see `review`). Does not touch teams/memberships at all.
        """
        if bool(artist_user_id) == bool(seatgeek_performer_id):
            raise ValidationError("Provide exactly one of artist_user_id or seatgeek_performer_id.")

        artist_user = None
        performer = None
        if artist_user_id is not None:
            artist_user = User.objects.filter(pk=artist_user_id, is_active=True).first()
            if not artist_user:
                raise exc.ArtistTargetNotFound(detail="No active user with that id.")
        else:
            performer = Performers.objects.filter(pk=seatgeek_performer_id).first()
            if not performer:
                raise exc.ArtistTargetNotFound(detail="No SeatGeek performer with that id.")

        try:
            with transaction.atomic():
                claim = ArtistClaim.objects.create(
                    claimant=claimant,
                    artist_user=artist_user,
                    seatgeek_performer=performer,
                    agency_roster_url=agency_roster_url,
                    confirmation_email=confirmation_email,
                    company_agency=company_agency,
                    business_email=business_email,
                    adder_role=adder_role,
                    representation=representation,
                    note=note,
                )
                for upload in documents or []:
                    ArtistClaimDocument.objects.create(claim=claim, file=upload)
        except IntegrityError:
            # uniq_live_claimant_artist_user / uniq_live_claimant_sg_performer.
            raise exc.DuplicateClaim()
        return claim

    @staticmethod
    def list_for(claimant: User, status: str | None = None) -> QuerySet[ArtistClaim]:
        qs = (
            ArtistClaim.objects
            .filter(claimant=claimant)
            .select_related("artist_user", "seatgeek_performer", "reviewed_by")
            .prefetch_related("documents")
        )
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-created_at")

    @staticmethod
    def get_for_viewer(viewer: User, claim_id: int) -> ArtistClaim:
        claim = (
            ArtistClaim.objects
            .select_related("artist_user", "seatgeek_performer", "claimant", "reviewed_by")
            .prefetch_related("documents")
            .filter(pk=claim_id)
            .first()
        )
        if not claim:
            raise exc.ClaimNotFound()
        if claim.claimant_id != viewer.pk and not viewer.is_admin:
            raise exc.NotYourClaim()
        return claim

    @staticmethod
    @transaction.atomic
    def withdraw(*, viewer: User, claim_id: int) -> None:
        """Let the claimant pull a still-pending claim - not a review
        decision, so it doesn't touch `reviewed_by`/`status: rejected`.
        """
        claim = ArtistClaimService.get_for_viewer(viewer, claim_id)
        if claim.claimant_id != viewer.pk:
            raise exc.NotYourClaim()
        if claim.status != ClaimStatus.PENDING:
            raise exc.AlreadyReviewed(detail="Only a pending claim can be withdrawn.")
        claim.delete()

    # --- Superadmin review queue ---

    @staticmethod
    def list_review_queue(status: str | None = None) -> QuerySet[ArtistClaim]:
        """Defaults to the pending queue; pass a `ClaimStatus` value to browse
        reviewed history instead - same shape as
        `apps.teams.services.ApprovalService.list_memberships`.
        """
        qs = ArtistClaim.objects.select_related("claimant", "artist_user", "seatgeek_performer", "reviewed_by")
        qs = qs.filter(status=status if status else ClaimStatus.PENDING)
        return qs.order_by("-created_at")

    @staticmethod
    def get_for_review(claim_id: int) -> ArtistClaim:
        claim = (
            ArtistClaim.objects
            .select_related("claimant", "artist_user", "seatgeek_performer", "reviewed_by")
            .prefetch_related("documents")
            .filter(pk=claim_id)
            .first()
        )
        if not claim:
            raise exc.ClaimNotFound()
        return claim

    @staticmethod
    @transaction.atomic
    def review(*, reviewer: User, claim_id: int, approve: bool, note: str = "") -> ArtistClaim:
        try:
            claim = ArtistClaim.objects.select_for_update().get(pk=claim_id)
        except ArtistClaim.DoesNotExist:
            raise exc.ClaimNotFound()
        if claim.status != ClaimStatus.PENDING:
            raise exc.AlreadyReviewed()

        claim.status = ClaimStatus.APPROVED if approve else ClaimStatus.REJECTED
        claim.reviewed_by = reviewer
        claim.reviewed_at = timezone.now()
        claim.review_note = note
        claim.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
        return claim

    # --- Search: artists as seen through the claim table ---

    @staticmethod
    def search_claimed_artists(*, search: str | None = None, status: str | None = None) -> list[dict]:
        """Distinct claimed artists (internal platform users + SeatGeek
        `Performers`), each carrying its own list of claimants.

        This searches *from the claim table outward* - an artist nobody has
        ever claimed simply never appears here (the regular catalog artist
        search at `/api/v1/catalog/artists/` is the place for "every artist";
        this one is "every artist someone claims to represent").

        `status` narrows to claims in that state (default: every claim,
        any status) so a caller can ask for e.g. only `approved` claimants;
        each claimant entry still carries its own `status`, since one artist
        can have a mix (one approved claimant, one still pending).
        """
        qs = (
            ArtistClaim.objects
            .select_related("claimant", "artist_user", "seatgeek_performer")
            .order_by("created_at")
        )
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(
                Q(artist_user__name__icontains=search) | Q(seatgeek_performer__name__icontains=search)
            )

        grouped: dict[tuple[str, str], dict] = {}
        for claim in qs:
            if claim.artist_user_id:
                key = ("internal", str(claim.artist_user_id))
                name = claim.artist_user.name
                # User.image is an ImageField (storage-relative path) - a
                # SeatGeek performer's is already a plain external URL
                # string. The serializer resolves either into an absolute
                # URL, so both are passed through as raw strings here.
                image = claim.artist_user.image.url if claim.artist_user.image else None
            else:
                key = ("seatgeek", claim.seatgeek_performer_id)
                name = claim.seatgeek_performer.name
                image = claim.seatgeek_performer.image or None

            entry = grouped.setdefault(key, {
                "source": key[0],
                "artist_user_id": claim.artist_user_id,
                "seatgeek_performer_id": claim.seatgeek_performer_id,
                "name": name,
                "image": image,
                "claimed_by": [],
            })
            entry["claimed_by"].append({
                "claim_id": claim.pk,
                "user": {"id": claim.claimant_id, "name": claim.claimant.name, "email": claim.claimant.email},
                "status": claim.status,
                "claimed_at": claim.created_at,
            })

        return list(grouped.values())
