"""Verify the three Bookings tabs (Pending / Confirmed / Past) for Buyer B."""
from apps.accounts.models import User
from apps.bookings.models import BookingOffer
from apps.bookings.serializers import BookingOfferSerializer
from apps.bookings.services import BookingService

buyer_a = User.objects.get(email="buyer.a@demo.getavails")
buyer_b = User.objects.get(email="buyer.b@demo.getavails")
artist_x = User.objects.get(email="artist.x@demo.getavails")

# Ensure a Past Event exists: a confirmed booking whose date already passed.
BookingOffer.objects.filter(recipient=buyer_b, title="Winter Gala").delete()
past = BookingService.create_offer(
    requester=buyer_a, artist_id=str(artist_x.id), recipient_id=buyer_b.id,
    title="Winter Gala", venue_name="Old Town Hall", event_date="2026-05-01", amount_cents=300000,
)
BookingService.accept(recipient=buyer_b, offer_id=past.id)
# Also a stale pending offer in the past should NOT appear under Past Events.
BookingOffer.objects.filter(recipient=buyer_b, title="Stale Pending").delete()
BookingService.create_offer(
    requester=buyer_a, artist_id=str(artist_x.id), recipient_id=buyer_b.id,
    title="Stale Pending", venue_name="Nowhere", event_date="2026-04-01", amount_cents=100000,
)

for tab in ("pending", "confirmed", "past"):
    qs = BookingService.list_received(buyer_b, status_filter=tab).order_by("event_date")
    rows = BookingOfferSerializer(qs, many=True).data
    print(f"\n=== tab: {tab}  (count={len(rows)}) ===")
    for r in rows:
        print(f"  #{r['id']:>3}  {r['title']:<24} {r['status']:<9} "
              f"{r['event_date']}  {r['venue_name']:<22} ${r['amount_cents']//100:,}")
