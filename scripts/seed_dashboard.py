"""Seed Buyer B's recipient dashboard to mirror the UI, then print the
actual serialized DashboardView response as JSON."""
import json

from apps.accounts.models import User
from apps.bookings.models import AvailabilitySlot, BookingOffer
from apps.bookings.serializers import ActivitySerializer, BookingOfferSerializer
from apps.bookings.services import BookingService, DashboardService

buyer_a = User.objects.get(email="buyer.a@demo.getavails")
buyer_b = User.objects.get(email="buyer.b@demo.getavails")
artist_x = User.objects.get(email="artist.x@demo.getavails")

# Reset demo state for a deterministic render.
BookingOffer.objects.filter(recipient=buyer_b).delete()
AvailabilitySlot.objects.filter(user=artist_x).delete()


def send(title, venue, day, amount):
    return BookingService.create_offer(
        requester=buyer_a, artist_id=str(artist_x.id), recipient_id=buyer_b.id,
        title=title, venue_name=venue, event_date=day, amount_cents=amount,
    )


# Pending incoming offers (Accept/Reject cards).
send("Summer Music Festival", "Central Park Arena", "2026-06-15", 500000)
send("Jazz Night", "Blue Note Club", "2026-06-25", 250000)
send("Corporate Event", "Grand Hotel Ballroom", "2026-07-05", 380000)

# Confirmed upcoming bookings (accept two, future dates).
spring = send("Spring Concert", "City Theater", "2026-06-20", 420000)
private = send("Private Event", "Riverside Venue", "2026-07-12", 600000)
BookingService.accept(recipient=buyer_b, offer_id=spring.id)
BookingService.accept(recipient=buyer_b, offer_id=private.id)

# Build the exact payload DashboardView returns.
kpis = DashboardService.kpis_for_user(buyer_b)
payload = {
    "success": True,
    "stats": kpis["stats"],
    "incoming_offers": BookingOfferSerializer(kpis["incoming_offers"], many=True).data,
    "upcoming_bookings": BookingOfferSerializer(kpis["upcoming_bookings"], many=True).data,
    "sent": kpis["sent"],
    "sent_offers": BookingOfferSerializer(kpis["sent_offers"], many=True).data,
    "recent_activities": ActivitySerializer(kpis["recent_activities"], many=True).data,
}

# Trim the heavy nested user objects for a readable preview of the offer cards.
def card(o):
    return {k: o[k] for k in ("id", "title", "venue_name", "event_date", "amount_cents", "status")}

preview = {
    "success": payload["success"],
    "stats": payload["stats"],
    "incoming_offers": [card(o) for o in payload["incoming_offers"]],
    "upcoming_bookings": [card(o) for o in payload["upcoming_bookings"]],
    "sent": payload["sent"],
    "recent_activities": [
        {k: a[k] for k in ("verb", "summary", "detail")} for a in payload["recent_activities"][:4]
    ],
}
print(json.dumps(preview, indent=2, default=str))
