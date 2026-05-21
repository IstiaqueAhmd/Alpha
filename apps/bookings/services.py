from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, QuerySet, Sum
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
    def create_offer(cls, *, requester: User, artist_id: str, **fields) -> BookingOffer:
        artist, sg_performer = cls._resolve_target(artist_id)
        if not artist and not sg_performer:
            raise NotFound("Artist not found.")
        if artist and artist.pk == requester.pk:
            raise ValidationError("You cannot send an offer to yourself.")

        offer = BookingOffer.objects.create(
            requester=requester,
            artist=artist,
            seatgeek_performer=sg_performer,
            **fields,
        )
        if artist:
            Activity.objects.create(
                user=artist,
                verb=Activity.Verb.OFFER_RECEIVED,
                summary="Offer received",
                detail=offer.title,
                metadata={"offer_id": offer.pk, "from_user_id": requester.pk},
            )
        return offer

    @staticmethod
    def _resolve_target(artist_id: str) -> tuple[User | None, SeatGeekPerformer | None]:
        raw = str(artist_id)
        if raw.isdigit():
            artist = User.objects.filter(
                pk=int(raw), role=User.Role.ARTIST, is_active=True,
            ).first()
            if artist:
                return artist, None
        sg = SeatGeekPerformer.objects.filter(pk=raw).first()
        return None, sg

    @classmethod
    @transaction.atomic
    def accept(cls, *, artist: User, offer_id: int) -> BookingOffer:
        offer = cls._get_owned_offer(artist, offer_id)
        if offer.status != BookingOffer.Status.PENDING:
            raise ValidationError("Offer is not pending.")

        offer.status = BookingOffer.Status.ACCEPTED
        offer.decided_at = timezone.now()
        offer.save(update_fields=["status", "decided_at", "updated_at"])

        AvailabilitySlot.objects.update_or_create(
            user=artist, date=offer.event_date,
            defaults={"status": AvailabilitySlot.Status.BOOKED, "note": offer.title},
        )
        Activity.objects.create(
            user=artist, verb=Activity.Verb.OFFER_ACCEPTED,
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
    def reject(cls, *, artist: User, offer_id: int) -> BookingOffer:
        offer = cls._get_owned_offer(artist, offer_id)
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
    def list_for_artist(artist: User, *, status_filter: str | None = None) -> QuerySet[BookingOffer]:
        qs = BookingOffer.objects.select_related("requester", "artist").filter(artist=artist)
        if status_filter == "pending":
            qs = qs.filter(status=BookingOffer.Status.PENDING)
        elif status_filter == "confirmed":
            qs = qs.filter(status=BookingOffer.Status.ACCEPTED, event_date__gte=timezone.now().date())
        elif status_filter == "past":
            qs = qs.filter(event_date__lt=timezone.now().date())
        return qs

    @staticmethod
    def list_for_requester(user: User) -> QuerySet[BookingOffer]:
        return BookingOffer.objects.select_related("requester", "artist").filter(requester=user)

    @staticmethod
    def _get_owned_offer(artist: User, offer_id: int) -> BookingOffer:
        offer = BookingOffer.objects.filter(pk=offer_id, artist=artist).first()
        if not offer:
            raise NotFound("Offer not found.")
        return offer


class DashboardService:
    @staticmethod
    def kpis_for_artist(artist: User) -> dict:
        today = timezone.now().date()
        offers = BookingOffer.objects.filter(artist=artist)

        active_offers = offers.filter(status=BookingOffer.Status.PENDING).count()
        confirmed_bookings = offers.filter(
            status=BookingOffer.Status.ACCEPTED, event_date__gte=today
        ).count()

        period_start = today.replace(day=1)
        prev_period_end = period_start - timedelta(days=1)
        prev_period_start = prev_period_end.replace(day=1)

        current_earnings = offers.filter(
            status__in=[BookingOffer.Status.ACCEPTED, BookingOffer.Status.COMPLETED],
            event_date__gte=period_start,
        ).aggregate(total=Sum("amount_cents"))["total"] or 0

        previous_earnings = offers.filter(
            status__in=[BookingOffer.Status.ACCEPTED, BookingOffer.Status.COMPLETED],
            event_date__gte=prev_period_start,
            event_date__lte=prev_period_end,
        ).aggregate(total=Sum("amount_cents"))["total"] or 0

        total_earnings = offers.filter(
            status__in=[BookingOffer.Status.ACCEPTED, BookingOffer.Status.COMPLETED],
        ).aggregate(total=Sum("amount_cents"))["total"] or 0

        if previous_earnings:
            growth = float(Decimal(current_earnings - previous_earnings) / Decimal(previous_earnings)) * 100
        else:
            growth = 100.0 if current_earnings else 0.0

        upcoming = offers.filter(
            status=BookingOffer.Status.ACCEPTED, event_date__gte=today
        ).order_by("event_date")[:5]
        incoming = offers.filter(status=BookingOffer.Status.PENDING).order_by("-created_at")[:5]
        recent_activities = Activity.objects.filter(user=artist).order_by("-created_at")[:10]

        return {
            "active_offers": active_offers,
            "confirmed_bookings": confirmed_bookings,
            "total_earnings_cents": total_earnings,
            "growth_percent": round(growth, 2),
            "incoming_offers": list(incoming),
            "upcoming_bookings": list(upcoming),
            "recent_activities": list(recent_activities),
        }


class ActivityService:
    @staticmethod
    def list_for(user: User) -> QuerySet[Activity]:
        return Activity.objects.filter(user=user).order_by("-created_at")
