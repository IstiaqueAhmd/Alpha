"""Tests for the unified internal + SeatGeek artist search API.

Covers:
* shared response shape (`booked_dates`, `available_ranges`) for both sources
* `available_on` excludes internal artists *and* SG performers (single-day + multi-day events)
* `genres` filter applies to both sources
* `favorites_only=true` skips SG entirely
* detail endpoint returns 1-year availability for both sources
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as dt_tz

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.bookings.models import AvailabilitySlot
from apps.catalog.models import ArtistProfile, Favorite, Genre
from apps.seatgeek.models import (
    Events,
    PerformerEvents,
    PerformerGenres,
    Performers,
    Venues,
)


def _now():
    return datetime.now(tz=dt_tz.utc)


class ArtistSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.now().date()

        cls.rock = Genre.objects.create(name="Rock", slug="rock")
        cls.jazz = Genre.objects.create(name="Jazz", slug="jazz")

        # Internal artist with bookings on +3, +4 (consecutive), +10; soft hold +20.
        cls.alice_user = User.objects.create_user(
            email="alice@example.com",
            password="testpass123",
            name="Alice Internal",
            role=User.Role.ARTIST,
        )
        cls.alice = ArtistProfile.objects.create(
            user=cls.alice_user, bio="Folk-rock", location="Brooklyn, NY", is_published=True,
        )
        cls.alice.genres.add(cls.rock)
        for offset, status, note in [
            (3, AvailabilitySlot.Status.BOOKED, "Studio"),
            (4, AvailabilitySlot.Status.BOOKED, "Studio"),
            (10, AvailabilitySlot.Status.BOOKED, "Festival"),
            (20, AvailabilitySlot.Status.SOFT_HOLD, "Tour hold"),
        ]:
            AvailabilitySlot.objects.create(
                user=cls.alice_user,
                date=cls.today + timedelta(days=offset),
                status=status,
                note=note,
            )

        # Internal artist with no bookings.
        cls.bob_user = User.objects.create_user(
            email="bob@example.com",
            password="testpass123",
            name="Bob Internal",
            role=User.Role.ARTIST,
        )
        cls.bob = ArtistProfile.objects.create(
            user=cls.bob_user, bio="Jazz sax", location="Brooklyn, NY", is_published=True,
        )
        cls.bob.genres.add(cls.jazz)

        # SG venue.
        cls.venue = Venues.objects.create(
            id=str(uuid.uuid4()),
            provider_name="seatgeek",
            provider_id="venue-1",
            provider_slug="msg",
            provider_url="https://example.com/msg",
            name="Madison Square Garden",
            address="4 Pennsylvania Plaza",
            city="New York",
            state="NY",
            postal_code="10001",
            country="US",
            lat=40.7505,
            long=-73.9934,
            capacity=20000,
            created_at=_now(),
            updated_at=_now(),
        )

        # SG performer A: booked +5 (single-day) and +30..+32 (multi-day range).
        cls.perf_busy = Performers.objects.create(
            id=str(uuid.uuid4()),
            name="Busy Star",
            provider_id="perf-busy",
            provider_name="seatgeek",
            url="https://example.com/busy",
            image="",
            score=80,
            created_at=_now(),
            updated_at=_now(),
        )
        PerformerGenres.objects.create(
            id=str(uuid.uuid4()),
            performer=cls.perf_busy,
            genre="rock",
            created_at=_now(),
            updated_at=_now(),
        )
        cls.ev_single = Events.objects.create(
            id=str(uuid.uuid4()),
            venue=cls.venue,
            provider_name="seatgeek",
            provider_id="ev-1",
            name="MSG Show",
            url="",
            location_name="MSG",
            location_url="",
            start_date=cls.today + timedelta(days=5),
            end_date=cls.today + timedelta(days=5),
            address="",
            created_at=_now(),
            updated_at=_now(),
        )
        cls.ev_range = Events.objects.create(
            id=str(uuid.uuid4()),
            venue=cls.venue,
            provider_name="seatgeek",
            provider_id="ev-2",
            name="3-Night Festival",
            url="",
            location_name="Festival",
            location_url="",
            start_date=cls.today + timedelta(days=30),
            end_date=cls.today + timedelta(days=32),
            address="",
            created_at=_now(),
            updated_at=_now(),
        )
        for ev in (cls.ev_single, cls.ev_range):
            PerformerEvents.objects.create(
                id=str(uuid.uuid4()),
                performer=cls.perf_busy,
                event=ev,
                created_at=_now(),
                updated_at=_now(),
            )

        # SG performer B: no events.
        cls.perf_free = Performers.objects.create(
            id=str(uuid.uuid4()),
            name="Free Star",
            provider_id="perf-free",
            provider_name="seatgeek",
            url="https://example.com/free",
            image="",
            score=70,
            created_at=_now(),
            updated_at=_now(),
        )
        PerformerGenres.objects.create(
            id=str(uuid.uuid4()),
            performer=cls.perf_free,
            genre="jazz",
            created_at=_now(),
            updated_at=_now(),
        )

    def _names(self, results):
        return [r.get("name") or (r.get("user") or {}).get("name") for r in results]

    def test_list_returns_both_sources_with_unified_shape(self):
        resp = self.client.get(reverse("catalog:artists-list"))
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["count"], 4)
        for row in body["results"]:
            self.assertIn(row["source"], {"internal", "seatgeek"})
            self.assertIn("booked_dates", row)
            self.assertIn("available_ranges", row)

    def test_internal_artist_booked_dates_and_year_long_free_ranges(self):
        resp = self.client.get(reverse("catalog:artists-list"))
        body = resp.json()
        alice_row = next(r for r in body["results"] if r.get("user", {}).get("email") == "alice@example.com")

        # 3 booked dates (soft-hold is not booked).
        self.assertEqual(len(alice_row["booked_dates"]), 3)
        for b in alice_row["booked_dates"]:
            self.assertEqual(b["start_date"], b["end_date"])  # single-day slots

        # Free ranges span ~1 year, with gaps around the blocked dates.
        first = alice_row["available_ranges"][0]
        last = alice_row["available_ranges"][-1]
        from datetime import date

        last_end = date.fromisoformat(last["end"])
        self.assertGreaterEqual(
            (last_end - self.today).days,
            360,
            f"available_ranges should cover ~1 year, got last={last['end']}",
        )
        # First free range starts today.
        self.assertEqual(first["start"], self.today.isoformat())

    def test_sg_performer_booked_event_ranges_and_free_ranges(self):
        resp = self.client.get(reverse("catalog:artist-detail", args=[self.perf_busy.id]))
        self.assertEqual(resp.status_code, 200, resp.content)
        p = resp.json()["artist"]
        self.assertEqual(p["source"], "seatgeek")
        self.assertEqual(len(p["booked_dates"]), 2)

        # Multi-day event preserves its full range.
        range_entry = next(b for b in p["booked_dates"] if b["start_date"] != b["end_date"])
        self.assertEqual(range_entry["start_date"], (self.today + timedelta(days=30)).isoformat())
        self.assertEqual(range_entry["end_date"], (self.today + timedelta(days=32)).isoformat())
        self.assertEqual(range_entry["venue"], "Madison Square Garden")
        self.assertEqual(range_entry["city"], "New York")

        # Free ranges = gaps; expect at least 3 (before +5, between +5 and +30, after +32).
        self.assertGreaterEqual(len(p["available_ranges"]), 3)

    def test_available_on_excludes_internal_and_sg(self):
        target = (self.today + timedelta(days=5)).isoformat()
        resp = self.client.get(reverse("catalog:artists-list") + f"?available_on={target}")
        names = self._names(resp.json()["results"])
        self.assertNotIn("Busy Star", names, names)
        self.assertIn("Free Star", names, names)

    def test_available_on_falls_inside_multi_day_event(self):
        target = (self.today + timedelta(days=31)).isoformat()
        resp = self.client.get(reverse("catalog:artists-list") + f"?available_on={target}")
        names = self._names(resp.json()["results"])
        self.assertNotIn("Busy Star", names, names)

    def test_available_on_excludes_internal_booked_artist(self):
        target = (self.today + timedelta(days=3)).isoformat()
        resp = self.client.get(reverse("catalog:artists-list") + f"?available_on={target}")
        names = self._names(resp.json()["results"])
        self.assertNotIn("Alice Internal", names, names)
        self.assertIn("Bob Internal", names, names)

    def test_available_on_excludes_internal_soft_hold(self):
        target = (self.today + timedelta(days=20)).isoformat()
        resp = self.client.get(reverse("catalog:artists-list") + f"?available_on={target}")
        names = self._names(resp.json()["results"])
        self.assertNotIn("Alice Internal", names, names)

    def test_genre_filter_applies_to_both_sources(self):
        resp = self.client.get(reverse("catalog:artists-list") + "?genres=jazz")
        names = self._names(resp.json()["results"])
        self.assertIn("Bob Internal", names, names)
        self.assertIn("Free Star", names, names)
        self.assertNotIn("Alice Internal", names, names)
        self.assertNotIn("Busy Star", names, names)

    def test_query_filter_applies_to_both_sources(self):
        resp = self.client.get(reverse("catalog:artists-list") + "?q=star")
        names = self._names(resp.json()["results"])
        self.assertEqual(sorted(names), ["Busy Star", "Free Star"])

    def test_available_range_excludes_artists_with_overlap(self):
        # Alice has booked +3, +4, +10 — range +2..+5 overlaps two of them.
        # Busy Star has event on +5 — overlaps the same range.
        # Bob & Free Star have nothing in window → should appear.
        frm = (self.today + timedelta(days=2)).isoformat()
        to = (self.today + timedelta(days=5)).isoformat()
        resp = self.client.get(
            reverse("catalog:artists-list") + f"?available_from={frm}&available_to={to}"
        )
        names = self._names(resp.json()["results"])
        self.assertNotIn("Alice Internal", names, names)
        self.assertNotIn("Busy Star", names, names)
        self.assertIn("Bob Internal", names, names)
        self.assertIn("Free Star", names, names)

    def test_available_range_clear_window_keeps_everyone(self):
        # +6..+9 falls between Alice's bookings and Busy Star's events — nobody overlaps.
        frm = (self.today + timedelta(days=6)).isoformat()
        to = (self.today + timedelta(days=9)).isoformat()
        resp = self.client.get(
            reverse("catalog:artists-list") + f"?available_from={frm}&available_to={to}"
        )
        names = self._names(resp.json()["results"])
        self.assertEqual(sorted(names), ["Alice Internal", "Bob Internal", "Busy Star", "Free Star"])

    def test_available_on_combined_with_available_to_acts_as_range(self):
        # Regression: `?available_on=X&available_to=Y` used to silently drop the `to`.
        # Range +4..+5 must still exclude Alice (+4 booked) and Busy Star (+5 event).
        frm = (self.today + timedelta(days=4)).isoformat()
        to = (self.today + timedelta(days=5)).isoformat()
        resp = self.client.get(
            reverse("catalog:artists-list") + f"?available_on={frm}&available_to={to}"
        )
        names = self._names(resp.json()["results"])
        self.assertNotIn("Alice Internal", names, names)
        self.assertNotIn("Busy Star", names, names)
        self.assertIn("Bob Internal", names, names)
        self.assertIn("Free Star", names, names)

    def test_available_range_reversed_is_normalized(self):
        # Swapped from/to should still work — service swaps them silently.
        later = (self.today + timedelta(days=5)).isoformat()
        earlier = (self.today + timedelta(days=4)).isoformat()
        resp = self.client.get(
            reverse("catalog:artists-list") + f"?available_from={later}&available_to={earlier}"
        )
        names = self._names(resp.json()["results"])
        self.assertNotIn("Alice Internal", names, names)
        self.assertNotIn("Busy Star", names, names)

    def test_available_range_spans_multi_day_sg_event(self):
        # +29..+33 brackets Busy Star's 3-night festival (+30..+32) on both sides.
        frm = (self.today + timedelta(days=29)).isoformat()
        to = (self.today + timedelta(days=33)).isoformat()
        resp = self.client.get(
            reverse("catalog:artists-list") + f"?available_from={frm}&available_to={to}"
        )
        names = self._names(resp.json()["results"])
        self.assertNotIn("Busy Star", names, names)

    def test_favorites_only_skips_seatgeek(self):
        # The API only accepts JWTAuthentication (no SessionAuthentication), so force_login
        # would leave request.user unauthenticated. Issue a real token instead.
        token = RefreshToken.for_user(self.alice_user).access_token
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        # No favorites yet.
        resp = self.client.get(reverse("catalog:artists-list") + "?favorites_only=true", **auth)
        body = resp.json()
        self.assertEqual(body["count"], 0)

        # Favorite Bob; only Bob should appear (no SG bleed-through).
        Favorite.objects.create(user=self.alice_user, artist=self.bob)
        resp = self.client.get(reverse("catalog:artists-list") + "?favorites_only=true", **auth)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["source"], "internal")
        self.assertEqual(body["results"][0]["user"]["email"], "bob@example.com")


class ArtistRadiusFilterTests(TestCase):
    """End-to-end coverage of the `latitude`/`longitude`/`radius_miles` filter for both sources.

    Internal artists are filtered by their own `ArtistProfile.latitude`/`longitude`.
    SG performers have no own location, so they're filtered via their events' venue coordinates —
    a performer is "near" if ANY of their events lives at a venue inside the radius.
    """

    # Reference points
    NYC_LAT, NYC_LNG = 40.7128, -74.0060
    BROOKLYN_LAT, BROOKLYN_LNG = 40.6782, -73.9442      # ~6 mi from NYC
    CHICAGO_LAT, CHICAGO_LNG = 41.8781, -87.6298        # ~789 mi from NYC
    # ~33 mi from NYC but inside the 25-mi bounding box (rectangular pre-filter)
    BBOX_CORNER_LAT, BBOX_CORNER_LNG = 41.05, -73.55

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.now().date()
        cls.rock = Genre.objects.create(name="Rock", slug="rock")
        cls.jazz = Genre.objects.create(name="Jazz", slug="jazz")

        # ---- Internal artists ----
        cls.nyc_user = User.objects.create_user(
            email="nyc@example.com", password="testpass123",
            name="NYC Artist", role=User.Role.ARTIST,
        )
        cls.nyc_artist = ArtistProfile.objects.create(
            user=cls.nyc_user, is_published=True,
            latitude=cls.BROOKLYN_LAT, longitude=cls.BROOKLYN_LNG,
        )
        cls.nyc_artist.genres.add(cls.rock)

        cls.chicago_user = User.objects.create_user(
            email="chi@example.com", password="testpass123",
            name="Chicago Artist", role=User.Role.ARTIST,
        )
        cls.chicago_artist = ArtistProfile.objects.create(
            user=cls.chicago_user, is_published=True,
            latitude=cls.CHICAGO_LAT, longitude=cls.CHICAGO_LNG,
        )
        cls.chicago_artist.genres.add(cls.jazz)

        cls.corner_user = User.objects.create_user(
            email="corner@example.com", password="testpass123",
            name="BBox Corner Artist", role=User.Role.ARTIST,
        )
        cls.corner_artist = ArtistProfile.objects.create(
            user=cls.corner_user, is_published=True,
            latitude=cls.BBOX_CORNER_LAT, longitude=cls.BBOX_CORNER_LNG,
        )

        cls.null_user = User.objects.create_user(
            email="null@example.com", password="testpass123",
            name="No-Location Artist", role=User.Role.ARTIST,
        )
        cls.null_artist = ArtistProfile.objects.create(
            user=cls.null_user, is_published=True,
            latitude=None, longitude=None,
        )

        # ---- SG venues at known locations ----
        cls.brooklyn_venue = Venues.objects.create(
            id=str(uuid.uuid4()),
            provider_name="seatgeek", provider_id="v-brooklyn", provider_slug="brk",
            provider_url="https://example.com/brk",
            name="Brooklyn Venue", address="", city="Brooklyn", state="NY",
            postal_code="11201", country="US",
            lat=cls.BROOKLYN_LAT, long=cls.BROOKLYN_LNG, capacity=1000,
            created_at=_now(), updated_at=_now(),
        )
        cls.chicago_venue = Venues.objects.create(
            id=str(uuid.uuid4()),
            provider_name="seatgeek", provider_id="v-chicago", provider_slug="chi",
            provider_url="https://example.com/chi",
            name="Chicago Venue", address="", city="Chicago", state="IL",
            postal_code="60601", country="US",
            lat=cls.CHICAGO_LAT, long=cls.CHICAGO_LNG, capacity=1000,
            created_at=_now(), updated_at=_now(),
        )

        # ---- SG performers ----
        # Nearby: has an event at Brooklyn venue.
        cls.sg_nearby = Performers.objects.create(
            id=str(uuid.uuid4()), name="Nearby SG Star",
            provider_id="perf-near", provider_name="seatgeek",
            url="https://example.com/near", image="", score=80,
            created_at=_now(), updated_at=_now(),
        )
        cls._link_event(cls.sg_nearby, cls.brooklyn_venue, days_offset=200)

        # Distant: only Chicago events.
        cls.sg_distant = Performers.objects.create(
            id=str(uuid.uuid4()), name="Distant SG Star",
            provider_id="perf-far", provider_name="seatgeek",
            url="https://example.com/far", image="", score=70,
            created_at=_now(), updated_at=_now(),
        )
        cls._link_event(cls.sg_distant, cls.chicago_venue, days_offset=200)

        # Touring: plays Chicago AND Brooklyn — should be matched by either anchor.
        cls.sg_touring = Performers.objects.create(
            id=str(uuid.uuid4()), name="Touring SG Star",
            provider_id="perf-tour", provider_name="seatgeek",
            url="https://example.com/tour", image="", score=90,
            created_at=_now(), updated_at=_now(),
        )
        cls._link_event(cls.sg_touring, cls.chicago_venue, days_offset=150)
        cls._link_event(cls.sg_touring, cls.brooklyn_venue, days_offset=180)

        # No-events: no derivable footprint.
        cls.sg_no_events = Performers.objects.create(
            id=str(uuid.uuid4()), name="Eventless SG Star",
            provider_id="perf-none", provider_name="seatgeek",
            url="https://example.com/none", image="", score=50,
            created_at=_now(), updated_at=_now(),
        )

    @classmethod
    def _link_event(cls, performer, venue, *, days_offset):
        ev = Events.objects.create(
            id=str(uuid.uuid4()),
            venue=venue,
            provider_name="seatgeek",
            provider_id=f"ev-{performer.provider_id}-{days_offset}",
            name=f"{performer.name} Show",
            url="", location_name=venue.name, location_url="",
            start_date=cls.today + timedelta(days=days_offset),
            end_date=cls.today + timedelta(days=days_offset),
            address="",
            created_at=_now(), updated_at=_now(),
        )
        PerformerEvents.objects.create(
            id=str(uuid.uuid4()),
            performer=performer, event=ev,
            created_at=_now(), updated_at=_now(),
        )

    def _names(self, results):
        return [r.get("name") or (r.get("user") or {}).get("name") for r in results]

    def _list(self, **params):
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(reverse("catalog:artists-list") + (f"?{qs}" if qs else ""))

    # ---- Internal-artist coverage ----

    def test_radius_includes_nearby_excludes_distant(self):
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertIn("NYC Artist", names, names)
        self.assertNotIn("Chicago Artist", names, names)

    def test_radius_excludes_artist_with_null_coordinates(self):
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertNotIn("No-Location Artist", names, names)

    def test_haversine_rejects_artist_inside_bbox_but_outside_circle(self):
        # Corner artist is inside the rectangular bbox for a 25-mi search around NYC
        # but ~33 mi away in straight-line distance — must be excluded by haversine.
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertNotIn("BBox Corner Artist", names, names)

    def test_haversine_accepts_artist_inside_circle(self):
        # Widening to 40 mi pulls the corner artist in (~33 mi away).
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=40)
        names = self._names(resp.json()["results"])
        self.assertIn("BBox Corner Artist", names, names)

    def test_large_radius_pulls_in_distant_artist(self):
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=1000)
        names = self._names(resp.json()["results"])
        self.assertIn("Chicago Artist", names, names)
        self.assertIn("NYC Artist", names, names)

    # ---- SG-performer coverage (via event venues) ----

    def test_geo_filter_includes_sg_with_nearby_event_venue(self):
        # Nearby SG Star plays at the Brooklyn venue (~6 mi from NYC).
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertIn("Nearby SG Star", names, names)

    def test_geo_filter_excludes_sg_with_only_distant_event_venues(self):
        # Distant SG Star only plays Chicago — must not appear in NYC 25-mi search.
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertNotIn("Distant SG Star", names, names)

    def test_geo_filter_excludes_sg_with_no_events(self):
        # Eventless SG Star has no derivable location → must not appear when geo is active.
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertNotIn("Eventless SG Star", names, names)

    def test_geo_filter_includes_touring_sg_when_any_venue_matches(self):
        # Touring SG Star plays both Chicago and Brooklyn — Brooklyn matches NYC, so include.
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertIn("Touring SG Star", names, names)

    def test_geo_filter_includes_touring_sg_when_searching_other_anchor(self):
        # Searching near Chicago — Touring SG plays there too.
        resp = self._list(latitude=self.CHICAGO_LAT, longitude=self.CHICAGO_LNG, radius_miles=25)
        names = self._names(resp.json()["results"])
        self.assertIn("Touring SG Star", names, names)
        self.assertIn("Distant SG Star", names, names)
        self.assertNotIn("Nearby SG Star", names, names)

    # ---- Cross-cutting ----

    def test_no_geo_params_keeps_all_seatgeek_performers(self):
        # Without geo filter, SG performers always appear regardless of where they tour.
        resp = self._list()
        names = self._names(resp.json()["results"])
        for sg_name in ("Nearby SG Star", "Distant SG Star", "Touring SG Star", "Eventless SG Star"):
            self.assertIn(sg_name, names, sg_name)

    def test_partial_geo_params_disable_the_filter(self):
        # Missing radius_miles → filter is skipped; everyone (including no-coord and eventless) comes through.
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG)
        names = self._names(resp.json()["results"])
        self.assertIn("NYC Artist", names)
        self.assertIn("Chicago Artist", names)
        self.assertIn("No-Location Artist", names)
        self.assertIn("Eventless SG Star", names)
        self.assertIn("Distant SG Star", names)

    def test_radius_zero_disables_the_filter(self):
        # radius_miles=0 is falsy in the service guard; treated as "no filter".
        resp = self._list(latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=0)
        names = self._names(resp.json()["results"])
        self.assertIn("Chicago Artist", names)
        self.assertIn("No-Location Artist", names)
        self.assertIn("Distant SG Star", names)
        self.assertIn("Eventless SG Star", names)

    def test_radius_combines_with_genre_filter(self):
        # Nearby NYC artist is rock; Chicago artist is jazz. Genre=rock + radius=25mi → only NYC.
        resp = self._list(
            latitude=self.NYC_LAT, longitude=self.NYC_LNG, radius_miles=25, genres="rock",
        )
        names = self._names(resp.json()["results"])
        self.assertIn("NYC Artist", names, names)
        self.assertNotIn("Chicago Artist", names, names)
        # No SG performer has a "rock" genre in this fixture, so SG should drop out.
        self.assertNotIn("Nearby SG Star", names, names)
