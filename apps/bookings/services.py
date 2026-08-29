from datetime import date

from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.seatgeek.models import Performers as SeatGeekPerformer

from .models import Activity, AvailabilitySlot, BookingOffer


class AvailabilityService:
    @staticmethod
    def list_for_artist(artist: User, start: date | None = None, end: date | None = None) -> QuerySet[AvailabilitySlot]:
        if artist.role != User.Role.ARTIST:
            raise ValidationError("Only artist accounts have availability.")
        qs = AvailabilitySlot.objects.filter(user=artist)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs.order_by("date")

    @staticmethod
    def upsert(artist: User, *, slot_date: date, status: str, note: str = "") -> AvailabilitySlot:
        if artist.role != User.Role.ARTIST:
            raise PermissionDenied("Only artists can manage availability.")
        slot, _ = AvailabilitySlot.objects.update_or_create(
            user=artist, date=slot_date,
            defaults={"status": status, "note": note},
        )
        Activity.objects.create(
            user=artist,
            verb=Activity.Verb.AVAILABILITY_UPDATED,
            summary="Availability updated",
            detail=f"{slot_date.isoformat()} → {status}",
            metadata={"date": slot_date.isoformat(), "status": status},
        )
        return slot

    @staticmethod
    def delete(artist: User, slot_date: date) -> None:
        AvailabilitySlot.objects.filter(user=artist, date=slot_date).delete()


class BookingService:
    @classmethod
    @transaction.atomic
    def create_offer(cls, *, requester: User, target_user_id: int | None = None, target_email: str = "", **fields) -> BookingOffer:
        target_user = None
        if target_user_id:
            target_user = User.objects.filter(pk=target_user_id, is_active=True).first()
            if not target_user:
                raise NotFound("Target user not found.")
            if target_user.pk == requester.pk:
                raise ValidationError("You cannot send an offer to yourself.")

        offer = BookingOffer.objects.create(
            requester=requester,
            target_user=target_user,
            target_email=target_email,
            **fields,
        )

        if target_user:
            Activity.objects.create(
                user=target_user,
                verb=Activity.Verb.OFFER_RECEIVED,
                summary="Offer received",
                detail=offer.title,
                metadata={"offer_id": offer.pk, "from_user_id": requester.pk},
            )
            # Send email
            print(f"Sending booking request email to {target_user.email}")
        elif target_email:
            # Send email
            print(f"Sending booking request email to {target_email}")
            
        return offer

    @classmethod
    @transaction.atomic
    def accept(cls, *, target_user: User, offer_id: int) -> BookingOffer:
        offer = cls._get_owned_offer(target_user, offer_id)
        if offer.status != BookingOffer.Status.PENDING:
            raise ValidationError("Offer is not pending.")

        offer.status = BookingOffer.Status.ACCEPTED
        offer.decided_at = timezone.now()
        offer.save(update_fields=["status", "decided_at", "updated_at"])

        Activity.objects.create(
            user=target_user, verb=Activity.Verb.OFFER_ACCEPTED,
            summary="Offer accepted", detail=offer.title,
            metadata={"offer_id": offer.pk},
        )
        Activity.objects.create(
            user=offer.requester, verb=Activity.Verb.OFFER_ACCEPTED,
            summary="Offer accepted", detail=offer.title,
            metadata={"offer_id": offer.pk},
        )
        return offer

    @classmethod
    @transaction.atomic
    def reject(cls, *, target_user: User, offer_id: int) -> BookingOffer:
        offer = cls._get_owned_offer(target_user, offer_id)
        if offer.status != BookingOffer.Status.PENDING:
            raise ValidationError("Offer is not pending.")
        offer.status = BookingOffer.Status.REJECTED
        offer.decided_at = timezone.now()
        offer.save(update_fields=["status", "decided_at", "updated_at"])
        Activity.objects.create(
            user=offer.requester, verb=Activity.Verb.OFFER_REJECTED,
            summary="Offer rejected", detail=offer.title,
            metadata={"offer_id": offer.pk},
        )
        return offer

    @staticmethod
    def list_received(target_user: User, *, status_filter: str | None = None) -> QuerySet[BookingOffer]:
        """Offers received by a talent-buyer, filtered to one Bookings tab.

        Tabs map to status_filter:
          - "pending"   -> Pending Offers   (awaiting accept/reject)
          - "confirmed" -> Confirmed Bookings (accepted, event still ahead)
          - "past"      -> Past Events       (settled, event already happened)
        """
        today = timezone.now().date()
        qs = BookingOffer.objects.select_related(
            "requester", "target_user"
        ).filter(target_user=target_user)
        if status_filter == "pending":
            qs = qs.filter(status=BookingOffer.Status.PENDING)
        elif status_filter == "confirmed":
            qs = qs.filter(status=BookingOffer.Status.ACCEPTED, event_date__gte=today)
        elif status_filter == "past":
            qs = qs.filter(
                status__in=[BookingOffer.Status.ACCEPTED, BookingOffer.Status.COMPLETED],
                event_date__lt=today,
            )
        return qs

    @staticmethod
    def list_for_requester(user: User) -> QuerySet[BookingOffer]:
        return BookingOffer.objects.select_related(
            "requester", "target_user"
        ).filter(requester=user)

    @staticmethod
    def _get_owned_offer(target_user: User, offer_id: int) -> BookingOffer:
        offer = BookingOffer.objects.filter(pk=offer_id, target_user=target_user).first()
        if not offer:
            raise NotFound("Offer not found.")
        return offer


class DashboardService:
    _SETTLED = [BookingOffer.Status.ACCEPTED, BookingOffer.Status.COMPLETED]
    _LIST_LIMIT = 5

    @classmethod
    def kpis_for_user(cls, user: User) -> dict:
        """Talent-buyer dashboard.

        Every user is a talent-buyer who both receives and sends booking
        requests. The screen is recipient-centric (incoming offers to
        accept/reject + upcoming bookings); the sent side is included for the
        buyer's own outgoing requests.
        """
        today = timezone.now().date()

        received = BookingOffer.objects.filter(target_user=user).select_related(
            "requester", "target_user"
        )
        sent = BookingOffer.objects.filter(requester=user).select_related(
            "requester", "target_user"
        )

        pending = received.filter(status=BookingOffer.Status.PENDING)
        accepted = received.filter(status=BookingOffer.Status.ACCEPTED)
        upcoming = accepted.filter(event_date__gte=today)

        earnings = received.filter(status__in=cls._SETTLED).aggregate(
            total=Sum("amount_cents")
        )["total"] or 0
        spend = sent.filter(status__in=cls._SETTLED).aggregate(
            total=Sum("amount_cents")
        )["total"] or 0

        return {
            # Four KPI cards (recipient side).
            "stats": {
                "incoming_offers": received.count(),          # total received, any status
                "pending_offers": pending.count(),            # awaiting accept/reject
                "upcoming_bookings": upcoming.count(),        # accepted, event still ahead
                "confirmed": accepted.count(),                # accepted, all-time
                "total_earnings_cents": earnings,
            },
            # "Incoming Offers" list -> the pending requests with Accept/Reject.
            "incoming_offers": list(pending.order_by("-created_at")[: cls._LIST_LIMIT]),
            # "Upcoming Bookings" list -> confirmed, soonest first.
            "upcoming_bookings": list(upcoming.order_by("event_date")[: cls._LIST_LIMIT]),
            # Buyer's own outgoing requests.
            "sent": {
                "pending": sent.filter(status=BookingOffer.Status.PENDING).count(),
                "accepted": sent.filter(status=BookingOffer.Status.ACCEPTED).count(),
                "total_spend_cents": spend,
            },
            "sent_offers": list(sent.order_by("-created_at")[: cls._LIST_LIMIT]),
            "recent_activities": list(
                Activity.objects.filter(user=user).order_by("-created_at")[:10]
            ),
        }


class ActivityService:
    @staticmethod
    def list_for(user: User) -> QuerySet[Activity]:
        return Activity.objects.filter(user=user).order_by("-created_at")
