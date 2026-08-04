from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from apps.inquiries.models import Inquiry
from apps.notifications.services import NotificationService
from apps.teams.models import ApprovalStatus, Team, TeamMembership
from apps.teams.services import TeamService

from .models import Offer, OfferDocument, OfferSignature

User = get_user_model()


class OfferService:
    @staticmethod
    def list_for(
        user: User,
        *,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        shared_with_me: bool = False,
        email: str | None = None,
    ) -> QuerySet[Offer]:
        member_team_ids = TeamMembership.objects.filter(
            user=user, status=ApprovalStatus.APPROVED
        ).values_list("team_id", flat=True)

        # shared_with_me narrows the scope to *only* the M2M shares - deliberately excluding
        # sender/receiver, so "shared with me" doesn't just re-list your own offers.
        if shared_with_me:
            scope = Q(shared_with_users=user) | Q(shared_with_teams__in=member_team_ids)
        else:
            scope = (
                Q(sender=user)
                | Q(receiver=user)
                | Q(shared_with_users=user)
                | Q(shared_with_teams__in=member_team_ids)
            )

        qs = (
            Offer.objects
            .select_related("sender", "receiver", "inquiry")
            .prefetch_related("shared_with_users", "shared_with_teams", "signatures")
            .filter(scope)
            .distinct()
        )

        if status:
            qs = qs.filter(status=status)

        if date_from:
            parsed = parse_date(date_from)
            if not parsed:
                raise ValidationError("date_from must be in YYYY-MM-DD format.")
            qs = qs.filter(date__gte=parsed)

        if date_to:
            parsed = parse_date(date_to)
            if not parsed:
                raise ValidationError("date_to must be in YYYY-MM-DD format.")
            qs = qs.filter(date__lte=parsed)

        if email:
            # Only the indexed accounts.User.email (sender/receiver's actual account) - same
            # rule as inquiries' email search.
            qs = qs.filter(
                Q(sender__email__icontains=email) | Q(receiver__email__icontains=email)
            ).distinct()

        return qs

    @staticmethod
    def get_for_viewer(viewer: User, offer_id: int) -> Offer:
        offer = OfferService.list_for(viewer).filter(pk=offer_id).first()
        if not offer:
            raise NotFound("Offer not found.")
        return offer

    @staticmethod
    def _apply_share(*, offer: Offer, actor: User, user_ids: list[int], team_ids: list[int]) -> None:
        if user_ids:
            users = User.objects.filter(pk__in=user_ids, is_active=True)
            offer.shared_with_users.add(*users)

        for team_id in team_ids:
            # get_for_member raises unless `actor` is that team's founder or an approved
            # member - you can only share into teams you actually belong to.
            team = TeamService.get_for_member(actor, team_id)
            offer.shared_with_teams.add(team)

    @classmethod
    @transaction.atomic
    def create(
        cls,
        *,
        sender: User,
        inquiry_id: int | None = None,
        receiver_id: int | None = None,
        signature=None,
        files: list | None = None,
        user_ids: list[int] | None = None,
        team_ids: list[int] | None = None,
        **fields,
    ) -> Offer:
        """Create an offer either against an accepted inquiry, or standalone to a receiver.

        Offers don't require an inquiry - `inquiry_id` is optional. When given, it still
        enforces the original rule (sender must be that inquiry's receiver, inquiry must be
        accepted, one offer per inquiry) and derives the receiver from it. Without it, the
        caller must name a `receiver_id` directly.

        `signature`/`files` are optional day-one attachments: only the sender is present at
        creation time, so only *their* signature can be bundled here - the receiver's (and
        any later re-signs, edits, or additional documents) still go through the dedicated
        sign/documents endpoints, since those happen later and by a different actor.

        `user_ids`/`team_ids` are optional initial shares - equivalent to calling `share()`
        right after creation, just folded into the same transaction.
        """
        inquiry = None
        if inquiry_id is not None:
            inquiry = Inquiry.objects.filter(pk=inquiry_id).first()
            if not inquiry:
                raise NotFound("Inquiry not found.")
            if inquiry.receiver_id != sender.pk:
                raise PermissionDenied("Only the inquiry receiver can generate an offer for it.")
            if inquiry.status != Inquiry.Status.ACCEPTED:
                raise ValidationError("The inquiry must be accepted before an offer can be generated.")
            if Offer.objects.filter(inquiry=inquiry).exists():
                raise ValidationError("An offer already exists for this inquiry.")
            receiver = inquiry.sender
        else:
            if not receiver_id:
                raise ValidationError("Provide either inquiry_id or receiver_id.")
            receiver = User.objects.filter(pk=receiver_id, is_active=True).first()
            if not receiver:
                raise NotFound("Receiver not found.")
            if receiver.pk == sender.pk:
                raise ValidationError("Cannot send an offer to yourself.")

        offer = Offer.objects.create(
            inquiry=inquiry,
            sender=sender,
            receiver=receiver,
            **fields,
        )

        if signature is not None:
            OfferSignature.objects.create(offer=offer, signer=sender, signature=signature)

        if files:
            OfferDocument.objects.bulk_create([OfferDocument(offer=offer, document=f) for f in files])

        if user_ids or team_ids:
            cls._apply_share(offer=offer, actor=sender, user_ids=user_ids or [], team_ids=team_ids or [])

        NotificationService.notify(
            recipient=offer.receiver,
            notification_type="offer.received",
            title=f"New offer from {sender.name or sender.email}",
            message=offer.artist_name,
            data={"offer_id": offer.id, "offer_uid": offer.uid},
        )
        return offer

    @classmethod
    def respond(cls, *, viewer: User, offer_id: int, decision: str) -> Offer:
        offer = cls.get_for_viewer(viewer, offer_id)
        if offer.receiver_id != viewer.pk:
            raise PermissionDenied("Only the receiver can respond to this offer.")
        if offer.status != Offer.Status.PENDING:
            raise ValidationError("This offer has already been responded to.")

        offer.status = decision
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "responded_at", "updated_at"])

        NotificationService.notify(
            recipient=offer.sender,
            notification_type=f"offer.{decision}",
            title=f"Your offer was {decision}",
            message=offer.artist_name,
            data={"offer_id": offer.id, "offer_uid": offer.uid},
        )
        return offer

    @classmethod
    def update(
        cls,
        *,
        actor: User,
        offer_id: int,
        user_ids: list[int] | None = None,
        team_ids: list[int] | None = None,
        **fields,
    ) -> Offer:
        offer = cls.get_for_viewer(actor, offer_id)
        if offer.sender_id != actor.pk:
            raise PermissionDenied("Only the offer sender can edit it.")
        if offer.status == Offer.Status.ACCEPTED:
            raise ValidationError("An accepted offer can no longer be edited.")

        was_rejected = offer.status == Offer.Status.REJECTED

        for field, value in fields.items():
            setattr(offer, field, value)
        if was_rejected:
            offer.status = Offer.Status.PENDING
            offer.responded_at = None
        offer.save()

        offer.signatures.all().delete()

        # Additive only - edit never removes an existing share, that's what unshare() is for.
        if user_ids or team_ids:
            cls._apply_share(offer=offer, actor=actor, user_ids=user_ids or [], team_ids=team_ids or [])

        NotificationService.notify(
            recipient=offer.receiver,
            notification_type="offer.updated",
            title=f"Offer updated by {actor.name or actor.email}",
            message=offer.artist_name,
            data={"offer_id": offer.id, "offer_uid": offer.uid},
        )
        return offer

    @classmethod
    def share(cls, *, actor: User, offer_id: int, user_ids: list[int], team_ids: list[int]) -> Offer:
        offer = cls.get_for_viewer(actor, offer_id)
        if offer.sender_id != actor.pk:
            raise PermissionDenied("Only the offer sender can share it.")

        cls._apply_share(offer=offer, actor=actor, user_ids=user_ids, team_ids=team_ids)
        return offer

    @classmethod
    def unshare(cls, *, actor: User, offer_id: int, user_ids: list[int], team_ids: list[int]) -> Offer:
        offer = cls.get_for_viewer(actor, offer_id)
        if offer.sender_id != actor.pk:
            raise PermissionDenied("Only the offer sender can remove shared access.")

        if user_ids:
            offer.shared_with_users.remove(*User.objects.filter(pk__in=user_ids))
        if team_ids:
            offer.shared_with_teams.remove(*Team.objects.filter(pk__in=team_ids))

        return offer

    @classmethod
    def add_signature(cls, *, actor: User, offer_id: int, signature) -> OfferSignature:
        # get_for_viewer already raises NotFound unless actor is the sender, the receiver,
        # a directly shared user, or an approved member of a shared team - anyone who
        # clears that is allowed to sign.
        offer = cls.get_for_viewer(actor, offer_id)

        obj, _ = OfferSignature.objects.update_or_create(
            offer=offer,
            signer=actor,
            defaults={"signature": signature, "signed_at": timezone.now()},
        )
        return obj

    @classmethod
    def add_documents(cls, *, actor: User, offer_id: int, files: list) -> list[OfferDocument]:
        offer = cls.get_for_viewer(actor, offer_id)
        return OfferDocument.objects.bulk_create(
            [OfferDocument(offer=offer, document=file) for file in files]
        )
