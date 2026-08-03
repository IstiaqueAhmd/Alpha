from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from apps.inquiries.models import Inquiry
from apps.notifications.services import NotificationService
from apps.teams.models import ApprovalStatus, TeamMembership
from apps.teams.services import TeamService

from .models import Offer, OfferDocument, OfferSignature

User = get_user_model()


class OfferService:
    @staticmethod
    def list_for(user: User) -> QuerySet[Offer]:
        member_team_ids = TeamMembership.objects.filter(
            user=user, status=ApprovalStatus.APPROVED
        ).values_list("team_id", flat=True)
        return (
            Offer.objects
            .select_related("sender", "receiver", "inquiry")
            .prefetch_related("shared_with_users", "shared_with_teams", "signatures")
            .filter(
                Q(sender=user)
                | Q(receiver=user)
                | Q(shared_with_users=user)
                | Q(shared_with_teams__in=member_team_ids)
            )
            .distinct()
        )

    @staticmethod
    def get_for_viewer(viewer: User, offer_id: int) -> Offer:
        offer = OfferService.list_for(viewer).filter(pk=offer_id).first()
        if not offer:
            raise NotFound("Offer not found.")
        return offer

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
    def update(cls, *, actor: User, offer_id: int, **fields) -> Offer:
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

        if user_ids:
            users = User.objects.filter(pk__in=user_ids, is_active=True)
            offer.shared_with_users.add(*users)

        for team_id in team_ids:
            team = TeamService.get_for_member(actor, team_id)
            offer.shared_with_teams.add(team)

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
