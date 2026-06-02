"""Populate the database with demo data for end-to-end testing.

Usage:
    python manage.py seed_demo            # idempotent — safe to re-run
    python manage.py seed_demo --reset    # delete prior demo data first

All demo users have email ending in `@demo.getavails.com` and password `Demo!Pass123`.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import NotificationPreferences
from apps.bookings.models import Activity, AvailabilitySlot, BookingOffer
from apps.catalog.models import (
    ArtistProfile,
    Favorite,
    Genre,
    RecentSearch,
    VenueProfile,
)
from apps.messaging.models import Conversation, Message

User = get_user_model()

DEMO_DOMAIN = "@demo.getavails.com"
DEMO_PASSWORD = "Demo!Pass123"


# --------------------------------------------------------------------------- #
# Static demo dataset                                                         #
# --------------------------------------------------------------------------- #


DEMO_USERS = [
    # Artists (mirroring UI mockups)
    {"key": "taylor",  "email": "taylor.swift" + DEMO_DOMAIN,  "name": "Taylor Swift",         "role": "artist",       "phone": "+1 555-0101"},
    {"key": "bruno",   "email": "bruno.mars" + DEMO_DOMAIN,    "name": "Bruno Mars",           "role": "artist",       "phone": "+1 555-0102"},
    {"key": "drake",   "email": "drake" + DEMO_DOMAIN,         "name": "Aubrey Drake Graham",  "role": "artist",       "phone": "+1 555-0103"},
    {"key": "rihanna", "email": "rihanna" + DEMO_DOMAIN,       "name": "Rihanna",              "role": "artist",       "phone": "+1 555-0104"},
    {"key": "kanye",   "email": "kanye.west" + DEMO_DOMAIN,    "name": "Kanye Omari West",     "role": "artist",       "phone": "+1 555-0105"},

    # Talent buyers
    {"key": "buyer1", "email": "sarah.mitchell" + DEMO_DOMAIN, "name": "Sarah Mitchell", "role": "talent-buyer", "phone": "+1 555-0201"},
    {"key": "buyer2", "email": "marcus.chen" + DEMO_DOMAIN,    "name": "Marcus Chen",    "role": "talent-buyer", "phone": "+1 555-0202"},

    # Agents
    {"key": "agent1", "email": "emma.rodriguez" + DEMO_DOMAIN, "name": "Emma Rodriguez", "role": "agent", "phone": "+1 555-0301"},
    {"key": "agent2", "email": "daiane.dany" + DEMO_DOMAIN,    "name": "Daiane Dany",    "role": "agent", "phone": "+1 555-0302"},

    # Venues
    {"key": "venue_blue",    "email": "blue.note" + DEMO_DOMAIN,        "name": "Blue Note Club",         "role": "venue", "phone": "+1 555-0401"},
    {"key": "venue_madison", "email": "madison.square" + DEMO_DOMAIN,   "name": "Madison Square Garden",  "role": "venue", "phone": "+1 555-0402"},
    {"key": "venue_central", "email": "central.park.arena" + DEMO_DOMAIN, "name": "Central Park Arena",   "role": "venue", "phone": "+1 555-0403"},

    # Organizers
    {"key": "org_summer", "email": "summer.fest" + DEMO_DOMAIN, "name": "Summer Festival Org", "role": "organizer", "phone": "+1 555-0501"},
    {"key": "org_tech",   "email": "tech.summit" + DEMO_DOMAIN, "name": "Tech Summit Org",     "role": "organizer", "phone": "+1 555-0502"},
]


DEMO_GENRES = [
    ("Pop", "pop"),
    ("Rock", "rock"),
    ("Hip Hop", "hip-hop"),
    ("R&B", "rnb"),
    ("EDM", "edm"),
    ("House", "house"),
    ("Techno", "techno"),
    ("Country", "country"),
    ("Jazz", "jazz"),
    ("Indie", "indie"),
    ("Electronic", "electronic"),
    ("Classical", "classical"),
]


ARTIST_PROFILES = {
    "taylor": {
        "bio": (
            "Taylor Swift is arguably the most multi-genre and prolific modern American "
            "singer-songwriter. With a discography that spans country, pop, indie, dance, "
            "and other categories, she has proven that an up-and-coming female songwriter "
            "can put out original music without always conforming to the wants of the "
            "industry."
        ),
        "location": "Los Angeles, CA",
        "latitude": 34.0522, "longitude": -118.2437,
        "experience_years": 18,
        "languages": ["English", "Spanish"],
        "base_price_cents": 1_500_000_00,
        "genres": ["pop", "country", "indie"],
    },
    "bruno": {
        "bio": "Bruno Mars is a multi-platinum-selling artist known for soulful pop and funk-infused hits across two decades.",
        "location": "Las Vegas, NV",
        "latitude": 36.1699, "longitude": -115.1398,
        "experience_years": 14,
        "languages": ["English"],
        "base_price_cents": 1_000_000_00,
        "genres": ["pop", "rnb"],
    },
    "drake": {
        "bio": "Aubrey Drake Graham is a Canadian rapper, singer, and songwriter who has shaped contemporary hip-hop and R&B.",
        "location": "Toronto, ON",
        "latitude": 43.6532, "longitude": -79.3832,
        "experience_years": 16,
        "languages": ["English"],
        "base_price_cents": 1_200_000_00,
        "genres": ["hip-hop", "rnb"],
    },
    "rihanna": {
        "bio": "Rihanna is a Barbadian singer, businesswoman, and one of the best-selling music artists of all time.",
        "location": "New York, NY",
        "latitude": 40.7128, "longitude": -74.0060,
        "experience_years": 20,
        "languages": ["English"],
        "base_price_cents": 1_300_000_00,
        "genres": ["pop", "rnb", "electronic"],
    },
    "kanye": {
        "bio": "Kanye Omari West is a producer-rapper whose work has redefined hip-hop production over multiple eras.",
        "location": "Chicago, IL",
        "latitude": 41.8781, "longitude": -87.6298,
        "experience_years": 22,
        "languages": ["English"],
        "base_price_cents": 1_100_000_00,
        "genres": ["hip-hop", "electronic"],
    },
}


VENUE_PROFILES = {
    "venue_blue": {
        "description": "Iconic jazz club in the heart of Greenwich Village.",
        "address": "131 W 3rd St, New York, NY 10012",
        "location": "New York, NY",
        "latitude": 40.7290, "longitude": -74.0010,
        "capacity": 220,
        "website": "https://www.bluenotejazz.com",
    },
    "venue_madison": {
        "description": "World-famous arena hosting top-tier sporting and music events.",
        "address": "4 Pennsylvania Plaza, New York, NY 10001",
        "location": "New York, NY",
        "latitude": 40.7505, "longitude": -73.9934,
        "capacity": 20000,
        "website": "https://www.msg.com",
    },
    "venue_central": {
        "description": "Outdoor amphitheater seating thousands under open skies.",
        "address": "Central Park, New York, NY",
        "location": "New York, NY",
        "latitude": 40.7829, "longitude": -73.9654,
        "capacity": 12000,
        "website": "https://www.centralparknyc.org",
    },
}


# --------------------------------------------------------------------------- #
# Command                                                                     #
# --------------------------------------------------------------------------- #


class Command(BaseCommand):
    help = "Populate the database with realistic demo data for testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data (any user with email ending @demo.getavails.com) before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        users = self._seed_users()
        self._seed_notification_preferences(users)
        genres = self._seed_genres()
        self._seed_artist_profiles(users, genres)
        self._seed_venue_profiles(users)
        self._seed_availability(users)
        offers = self._seed_offers(users)
        self._seed_favorites(users)
        self._seed_recent_searches(users)
        self._seed_conversations(users)
        self._seed_extra_activities(users)

        self.stdout.write(self.style.SUCCESS("\nDemo data seeded.\n"))
        self.stdout.write(f"Default password (all demo users): {DEMO_PASSWORD}\n")
        self.stdout.write("\nUsers:\n")
        for u in User.objects.filter(email__endswith=DEMO_DOMAIN).order_by("role", "email"):
            self.stdout.write(f"  [{u.role:13s}] {u.email}  —  {u.name}")

        self.stdout.write(
            f"\nGenres: {Genre.objects.count()}  |  "
            f"Artists: {ArtistProfile.objects.count()}  |  "
            f"Venues: {VenueProfile.objects.count()}  |  "
            f"Offers: {BookingOffer.objects.count()}  |  "
            f"Slots: {AvailabilitySlot.objects.count()}  |  "
            f"Convos: {Conversation.objects.count()}  |  "
            f"Messages: {Message.objects.count()}"
        )

    # ----------------------------------------------------------------------- #
    # Steps                                                                   #
    # ----------------------------------------------------------------------- #

    def _reset(self):
        deleted, _ = User.objects.filter(email__endswith=DEMO_DOMAIN).delete()
        self.stdout.write(f"Reset: removed {deleted} demo records (cascading).")

    def _seed_users(self) -> dict:
        users = {}
        for entry in DEMO_USERS:
            user, created = User.objects.update_or_create(
                email=entry["email"],
                defaults={
                    "name": entry["name"],
                    "role": entry["role"],
                    "phone": entry.get("phone", ""),
                    "is_active": True,
                    "email_verified_at": timezone.now(),
                },
            )
            if created or not user.has_usable_password():
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            users[entry["key"]] = user
        return users

    def _seed_notification_preferences(self, users: dict) -> None:
        for user in users.values():
            NotificationPreferences.objects.get_or_create(user=user)

    def _seed_genres(self) -> dict:
        genres = {}
        for name, slug in DEMO_GENRES:
            genre, _ = Genre.objects.update_or_create(slug=slug, defaults={"name": name})
            genres[slug] = genre
        return genres

    def _seed_artist_profiles(self, users: dict, genres: dict) -> None:
        for key, data in ARTIST_PROFILES.items():
            user = users[key]
            profile, _ = ArtistProfile.objects.update_or_create(
                user=user,
                defaults={
                    "bio": data["bio"],
                    "location": data["location"],
                    "latitude": data["latitude"],
                    "longitude": data["longitude"],
                    "experience_years": data["experience_years"],
                    "languages": data["languages"],
                    "base_price_cents": data["base_price_cents"],
                    "is_published": True,
                },
            )
            profile.genres.set([genres[slug] for slug in data["genres"] if slug in genres])

    def _seed_venue_profiles(self, users: dict) -> None:
        for key, data in VENUE_PROFILES.items():
            VenueProfile.objects.update_or_create(
                user=users[key],
                defaults={**data, "is_published": True},
            )

    def _seed_availability(self, users: dict) -> None:
        today = date.today()
        # Per artist: list of (offset_days, status)
        patterns = {
            "taylor":  [(2, "soft_hold"), (5, "booked"), (7, "soft_hold"), (12, "booked"), (14, "soft_hold"), (19, "booked"), (21, "soft_hold"), (26, "booked"), (28, "soft_hold")],
            "bruno":   [(3, "booked"), (4, "soft_hold"), (10, "booked"), (11, "soft_hold"), (17, "booked"), (24, "booked")],
            "drake":   [(2, "soft_hold"), (8, "booked"), (9, "soft_hold"), (15, "booked"), (16, "soft_hold"), (22, "booked")],
            "rihanna": [(1, "booked"), (3, "soft_hold"), (6, "booked"), (10, "soft_hold"), (13, "booked"), (17, "soft_hold"), (20, "booked"), (24, "soft_hold"), (27, "booked")],
            "kanye":   [(4, "soft_hold"), (11, "booked"), (18, "soft_hold"), (25, "booked")],
        }
        for key, slots in patterns.items():
            artist = users[key]
            for offset_days, status in slots:
                AvailabilitySlot.objects.update_or_create(
                    user=artist, date=today + timedelta(days=offset_days),
                    defaults={"status": status, "note": "Demo seed"},
                )

    def _seed_offers(self, users: dict) -> list:
        today = date.today()
        now = timezone.now()
        rows = [
            # Pending offers (Taylor's dashboard)
            {"r": "buyer1",  "a": "taylor", "title": "Summer Music Festival",  "d": today + timedelta(days=30), "venue": "Central Park Arena", "addr": "Central Park, NYC",       "amt": 5_000_00, "status": "pending"},
            {"r": "buyer2",  "a": "taylor", "title": "Jazz Night",             "d": today + timedelta(days=22), "venue": "Blue Note Club",     "addr": "131 W 3rd St, NYC",       "amt": 2_500_00, "status": "pending"},
            {"r": "agent1",  "a": "taylor", "title": "Corporate Event",        "d": today + timedelta(days=29), "venue": "Grand Hotel Ballroom", "addr": "5 Av, NYC",             "amt": 3_800_00, "status": "pending"},
            {"r": "buyer1",  "a": "taylor", "title": "Product Launch",         "d": today + timedelta(days=100), "venue": "Downtown Convention Center", "addr": "Las Vegas, NV",   "amt": 5_200_00, "status": "pending"},
            {"r": "org_tech", "a": "taylor", "title": "Annual Conference",     "d": today + timedelta(days=188), "venue": "City Sports Arena", "addr": "Chicago, IL",              "amt": 4_500_00, "status": "pending"},

            # Confirmed (Taylor)
            {"r": "agent2",  "a": "taylor", "title": "Spring Concert",         "d": today + timedelta(days=14), "venue": "City Theater",       "addr": "Manhattan, NYC",          "amt": 8_000_00, "status": "accepted"},
            {"r": "buyer1",  "a": "taylor", "title": "Private Event",          "d": today + timedelta(days=12), "venue": "Riverside Venue",    "addr": "Brooklyn, NYC",           "amt": 6_500_00, "status": "accepted"},

            # Past / completed (Taylor) — drives total earnings
            {"r": "agent1",  "a": "taylor", "title": "Pop Concert",            "d": today - timedelta(days=30), "venue": "Madison Square Garden", "addr": "MSG, NYC",             "amt": 7_500_00, "status": "accepted"},
            {"r": "buyer2",  "a": "taylor", "title": "Pop Concert",            "d": today - timedelta(days=60), "venue": "Madison Square Garden", "addr": "MSG, NYC",             "amt": 7_500_00, "status": "accepted"},
            {"r": "agent2",  "a": "taylor", "title": "Pop Concert",            "d": today - timedelta(days=90), "venue": "Madison Square Garden", "addr": "MSG, NYC",             "amt": 7_500_00, "status": "accepted"},
            {"r": "org_summer", "a": "taylor", "title": "Summer Music Festival", "d": today - timedelta(days=120), "venue": "Central Park Arena", "addr": "NYC",                 "amt": 5_000_00, "status": "accepted"},
            {"r": "buyer1",  "a": "taylor", "title": "Jazz Night",             "d": today - timedelta(days=150), "venue": "Blue Note Club",     "addr": "NYC",                    "amt": 2_500_00, "status": "accepted"},
            {"r": "buyer2",  "a": "taylor", "title": "Rock Festival",          "d": today - timedelta(days=200), "venue": "Central Park",       "addr": "NYC",                    "amt": 5_000_00, "status": "accepted"},

            # Rejected
            {"r": "buyer2",  "a": "taylor", "title": "Wedding Reception",      "d": today + timedelta(days=8),  "venue": "Hilton Hotel",       "addr": "Los Angeles, CA",         "amt": 3_000_00, "status": "rejected"},

            # Other artists — sprinkle in some to make the catalog dashboard non-empty
            {"r": "buyer1",  "a": "bruno",  "title": "New Year's Eve",         "d": today + timedelta(days=45), "venue": "MSG",                "addr": "NYC",                     "amt": 9_000_00, "status": "pending"},
            {"r": "agent1",  "a": "drake",  "title": "Album Release Party",    "d": today + timedelta(days=20), "venue": "Hollywood Bowl",     "addr": "Los Angeles, CA",         "amt": 8_500_00, "status": "accepted"},
            {"r": "venue_madison", "a": "rihanna", "title": "Headline Show",   "d": today + timedelta(days=60), "venue": "Madison Square Garden", "addr": "NYC",                  "amt": 12_000_00, "status": "pending"},
            {"r": "org_summer", "a": "kanye", "title": "Festival Headliner",   "d": today + timedelta(days=75), "venue": "Coachella Grounds",  "addr": "Indio, CA",               "amt": 11_000_00, "status": "accepted"},
        ]

        offers = []
        for od in rows:
            requester = users[od["r"]]
            artist = users[od["a"]]
            offer, _ = BookingOffer.objects.update_or_create(
                requester=requester,
                artist=artist,
                title=od["title"],
                event_date=od["d"],
                defaults={
                    "venue_name": od["venue"],
                    "address": od["addr"],
                    "amount_cents": od["amt"],
                    "budget_min_cents": int(od["amt"] * 0.85),
                    "budget_max_cents": int(od["amt"] * 1.2),
                    "status": od["status"],
                    "decided_at": now if od["status"] in ("accepted", "rejected") else None,
                    "contact_name": requester.name,
                    "contact_email": requester.email,
                    "contact_phone": requester.phone,
                    "notes": "Seeded demo offer.",
                },
            )
            if od["status"] == "accepted":
                AvailabilitySlot.objects.update_or_create(
                    user=artist, date=od["d"],
                    defaults={"status": "booked", "note": od["title"]},
                )
            offers.append(offer)
        return offers

    def _seed_favorites(self, users: dict) -> None:
        # Sarah Mitchell favorites Taylor and Drake
        for artist_key in ("taylor", "drake"):
            artist_profile = users[artist_key].artist_profile
            Favorite.objects.get_or_create(user=users["buyer1"], artist=artist_profile)
        # Marcus Chen favorites Bruno and Rihanna
        for artist_key in ("bruno", "rihanna"):
            artist_profile = users[artist_key].artist_profile
            Favorite.objects.get_or_create(user=users["buyer2"], artist=artist_profile)
        # Emma Rodriguez favorites Kanye
        Favorite.objects.get_or_create(
            user=users["agent1"], artist=users["kanye"].artist_profile
        )

    def _seed_recent_searches(self, users: dict) -> None:
        examples = [
            {"user": "buyer1", "query": "Taylor",        "location": "New York, NY",   "radius_miles": 50,  "genres": ["pop"], "target_date": None},
            {"user": "buyer1", "query": "",              "location": "Los Angeles, CA","radius_miles": 100, "genres": ["pop", "rnb"], "target_date": date.today() + timedelta(days=30)},
            {"user": "buyer2", "query": "Bruno",         "location": "Las Vegas, NV",  "radius_miles": 50,  "genres": [], "target_date": None},
            {"user": "agent1", "query": "",              "location": "Chicago, IL",    "radius_miles": 200, "genres": ["hip-hop"], "target_date": None},
        ]
        for ex in examples:
            user = users[ex.pop("user")]
            RecentSearch.objects.create(user=user, **ex)

    def _seed_conversations(self, users: dict) -> None:
        # Sarah Mitchell ↔ Taylor — matches the UI Messages screen verbatim
        self._make_conversation(
            users, "taylor", "buyer1",
            [
                ("taylor", "Hi! Thanks for reaching out. I'd love to discuss your event"),
                ("buyer1", "Great! We're planning a corporate event for June 15th"),
                ("taylor", "Perfect, I'm available that date. What's the expected guest count?"),
                ("buyer1", "Around 300 people. It's a product launch event"),
                ("taylor", "Sounds great! Looking forward to it"),
            ],
            base_offset_minutes=120,
        )

        # Marcus Chen ↔ Taylor — older conversation, two days ago
        self._make_conversation(
            users, "taylor", "buyer2",
            [
                ("buyer2", "Hi Taylor — checking availability for a private gig in Aspen."),
                ("taylor", "Sounds intriguing! What dates are you considering?"),
                ("buyer2", "Thank you for booking! Let me know if you need anything before then."),
            ],
            base_offset_minutes=24 * 60 + 30,
        )

        # Madison Square Garden (venue) ↔ Drake — last week
        self._make_conversation(
            users, "drake", "venue_madison",
            [
                ("venue_madison", "We'd love to host you for a 3-night residency."),
                ("drake", "I can definitely work with that budget."),
            ],
            base_offset_minutes=5 * 24 * 60,
        )

    def _make_conversation(self, users: dict, key_a: str, key_b: str, msgs, *, base_offset_minutes: int) -> None:
        from django.db.models import Count

        user_a = users[key_a]
        user_b = users[key_b]

        existing = (
            Conversation.objects
            .annotate(c=Count("participants"))
            .filter(participants=user_a)
            .filter(participants=user_b)
            .filter(c=2)
            .first()
        )
        convo = existing or Conversation.objects.create()
        if not existing:
            convo.participants.add(user_a, user_b)

        # Wipe prior messages so re-runs stay deterministic
        convo.messages.all().delete()

        base_time = timezone.now() - timedelta(minutes=base_offset_minutes)
        last = base_time
        for idx, (sender_key, body) in enumerate(msgs):
            sender = users[sender_key]
            msg = Message.objects.create(conversation=convo, sender=sender, body=body)
            msg.created_at = base_time + timedelta(minutes=idx * 15)
            msg.save(update_fields=["created_at"])
            last = msg.created_at

        convo.last_message_at = last
        convo.save(update_fields=["last_message_at"])

    def _seed_extra_activities(self, users: dict) -> None:
        taylor = users["taylor"]
        # Add curated activities for the Recent Activity panel on the dashboard.
        Activity.objects.create(
            user=taylor, verb=Activity.Verb.OFFER_ACCEPTED,
            summary="Offer accepted", detail="Spring Concert", metadata={},
        )
        Activity.objects.create(
            user=taylor, verb=Activity.Verb.AVAILABILITY_UPDATED,
            summary="Availability updated", detail="June dates blocked", metadata={},
        )
        Activity.objects.create(
            user=taylor, verb=Activity.Verb.MESSAGE_RECEIVED,
            summary="Message received", detail="From venue manager", metadata={},
        )
