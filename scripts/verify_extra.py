"""Verify the reject branch and a SeatGeek-subject offer (no calendar slot)."""
import uuid

from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import AvailabilitySlot, BookingOffer
from apps.bookings.services import BookingService
from apps.seatgeek.models import Performers


def banner(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


buyer_a = User.objects.get(email="buyer.a@demo.getavails")
buyer_b = User.objects.get(email="buyer.b@demo.getavails")
artist_x = User.objects.get(email="artist.x@demo.getavails")

banner("A. Reject path")
BookingOffer.objects.filter(requester=buyer_a, recipient=buyer_b,
                            title="Reject Demo").delete()
offer = BookingService.create_offer(
    requester=buyer_a, artist_id=str(artist_x.id), recipient_id=buyer_b.id,
    title="Reject Demo", event_date="2026-09-01", amount_cents=100000,
)
rejected = BookingService.reject(recipient=buyer_b, offer_id=offer.id)
print(f"  Offer #{offer.id} -> status={rejected.status} decided_at={rejected.decided_at}")
assert rejected.status == BookingOffer.Status.REJECTED
# A rejected offer must not book the artist's calendar.
assert not AvailabilitySlot.objects.filter(user=artist_x, date="2026-09-01").exists()
print("  OK: rejected, no calendar slot created")

banner("B. SeatGeek subject (external performer) -> accept must skip slot")
sg = Performers.objects.create(
    id=str(uuid.uuid4()), name="Demo SG Performer",
    provider_name="demo", provider_id=str(uuid.uuid4()),
    created_at=timezone.now(), updated_at=timezone.now(),
)
try:
    offer = BookingService.create_offer(
        requester=buyer_a, artist_id=sg.id, recipient_id=buyer_b.id,
        title="SG Demo", event_date="2026-10-01", amount_cents=200000,
    )
    print(f"  Offer #{offer.id}: subject_artist={offer.artist} "
          f"subject_sg={offer.seatgeek_performer.name} status={offer.status}")
    assert offer.artist_id is None
    assert offer.seatgeek_performer_id == sg.id

    accepted = BookingService.accept(recipient=buyer_b, offer_id=offer.id)
    print(f"  Accepted -> status={accepted.status}; "
          f"artist slots created = {AvailabilitySlot.objects.filter(date='2026-10-01').count()}")
    assert accepted.status == BookingOffer.Status.ACCEPTED
    # No internal artist on the offer, so no AvailabilitySlot should be touched.
    assert not AvailabilitySlot.objects.filter(date="2026-10-01").exists()
    print("  OK: SeatGeek subject accepted without touching any artist calendar")
finally:
    BookingOffer.objects.filter(seatgeek_performer=sg).delete()
    sg.delete()
    print("  (cleaned up temp SeatGeek performer row)")

banner("EXTRA CHECKS PASSED")
