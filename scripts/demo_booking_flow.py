"""Demo data + end-to-end verification for the talent-buyer booking flow.

Idempotent: creates clearly-labeled demo records (emails under @demo.getavails)
and exercises the real service layer (create_offer -> accept/reject -> dashboard).

Run: python manage.py shell -c "exec(open('scripts/demo_booking_flow.py').read())"
"""
from apps.accounts.models import User
from apps.bookings.models import AvailabilitySlot, BookingOffer
from apps.bookings.services import BookingService, DashboardService


def banner(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def get_buyer(email, name):
    user, created = User.objects.get_or_create(
        email=email,
        defaults={"name": name, "role": User.Role.TALENT_BUYER, "is_active": True},
    )
    if created:
        user.set_password("Demo1234!")
        user.save(update_fields=["password"])
    return user


def get_artist(email, name):
    user, _ = User.objects.get_or_create(
        email=email,
        defaults={"name": name, "role": User.Role.ARTIST, "is_active": True},
    )
    return user


banner("1. Demo users")
buyer_a = get_buyer("buyer.a@demo.getavails", "Demo Buyer A (sender)")
buyer_b = get_buyer("buyer.b@demo.getavails", "Demo Buyer B (recipient)")
artist_x = get_artist("artist.x@demo.getavails", "Demo Artist X (subject)")
print(f"  Buyer A  : id={buyer_a.id} role={buyer_a.role}")
print(f"  Buyer B  : id={buyer_b.id} role={buyer_b.role}")
print(f"  Artist X : id={artist_x.id} role={artist_x.role}")

# Clean any prior demo offers so the run is deterministic.
BookingOffer.objects.filter(requester=buyer_a, artist=artist_x).delete()
AvailabilitySlot.objects.filter(user=artist_x).delete()

banner("2. Buyer A sends a booking request about Artist X to Buyer B")
offer = BookingService.create_offer(
    requester=buyer_a,
    artist_id=str(artist_x.id),
    recipient_id=buyer_b.id,
    title="Summer Festival Headliner",
    event_date="2026-08-15",
    venue_name="Riverside Amphitheater",
    amount_cents=500000,
)
print(f"  Offer #{offer.id}: requester={offer.requester.email} "
      f"recipient={offer.recipient.email} subject_artist={offer.artist.email} "
      f"status={offer.status}")
assert offer.requester_id == buyer_a.id
assert offer.recipient_id == buyer_b.id
assert offer.artist_id == artist_x.id
assert offer.status == BookingOffer.Status.PENDING
print("  OK: stored as requester=A, recipient=B, subject=X, status=pending")

banner("3. Self-offer + non-talent-buyer recipient are rejected")
for label, rid in [("recipient = self (A)", buyer_a.id), ("recipient = artist (not TB)", artist_x.id)]:
    try:
        BookingService.create_offer(
            requester=buyer_a, artist_id=str(artist_x.id), recipient_id=rid,
            title="bad", event_date="2026-08-15",
        )
        print(f"  FAIL: {label} was allowed")
    except Exception as exc:
        print(f"  OK: {label} -> {type(exc).__name__}: {exc}")

banner("4. Visibility: A sees it as SENT, B sees it as RECEIVED")
sent = BookingService.list_for_requester(buyer_a)
recv = BookingService.list_received(buyer_b)
print(f"  A list_for_requester -> {[o.id for o in sent]}")
print(f"  B list_received      -> {[o.id for o in recv]}")
assert offer.id in [o.id for o in sent]
assert offer.id in [o.id for o in recv]
# A must NOT see it on the received side; B must NOT see it on the sent side.
assert offer.id not in [o.id for o in BookingService.list_received(buyer_a)]
assert offer.id not in [o.id for o in BookingService.list_for_requester(buyer_b)]
print("  OK: directional visibility correct")

banner("5. Only the recipient (B) can accept; A cannot")
try:
    BookingService.accept(recipient=buyer_a, offer_id=offer.id)
    print("  FAIL: sender A was able to accept")
except Exception as exc:
    print(f"  OK: A accept blocked -> {type(exc).__name__}: {exc}")

accepted = BookingService.accept(recipient=buyer_b, offer_id=offer.id)
print(f"  B accepted -> status={accepted.status} decided_at={accepted.decided_at}")
assert accepted.status == BookingOffer.Status.ACCEPTED

slot = AvailabilitySlot.objects.filter(user=artist_x, date=accepted.event_date).first()
print(f"  Artist X slot on {accepted.event_date}: "
      f"{slot.status if slot else 'NONE'}")
assert slot and slot.status == AvailabilitySlot.Status.BOOKED
print("  OK: acceptance booked the internal artist's calendar slot")

banner("6. Dashboards reflect both sides")
da = DashboardService.kpis_for_user(buyer_a)
db = DashboardService.kpis_for_user(buyer_b)
print(f"  Buyer A (sender)   as_booker    = {da['as_booker']}")
print(f"  Buyer A (sender)   as_recipient = {da['as_recipient']}")
print(f"  Buyer B (recipient) as_recipient = {db['as_recipient']}")
print(f"  Buyer B (recipient) as_booker    = {db['as_booker']}")
assert da["as_booker"]["accepted_sent"] >= 1
assert da["as_booker"]["total_spend_cents"] >= 500000
assert db["as_recipient"]["confirmed_bookings"] >= 1
assert db["as_recipient"]["total_earnings_cents"] >= 500000
print("  OK: A shows spend on booker side, B shows earnings on recipient side")

banner("ALL CHECKS PASSED")
