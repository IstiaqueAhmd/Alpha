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
        self.client.force_login(self.alice_user)
        # No favorites yet.
        resp = self.client.get(reverse("catalog:artists-list") + "?favorites_only=true")
        body = resp.json()
        self.assertEqual(body["count"], 0)

        # Favorite Bob; only Bob should appear (no SG bleed-through).
        Favorite.objects.create(user=self.alice_user, artist=self.bob)
        resp = self.client.get(reverse("catalog:artists-list") + "?favorites_only=true")
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["source"], "internal")
        self.assertEqual(body["results"][0]["user"]["email"], "bob@example.com")
