import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.artist_claims.exceptions import AlreadyReviewed, DuplicateClaim
from apps.artist_claims.models import ArtistClaim, ClaimStatus
from apps.artist_claims.services import ArtistClaimService
from apps.seatgeek.models import Performers

User = get_user_model()


def make_user(email: str, **kwargs) -> User:
    return User.objects.create_user(email=email, name=email.split("@")[0], password="pass12345", **kwargs)


def make_performer(name: str = "Some Band") -> Performers:
    return Performers.objects.create(
        id=str(uuid.uuid4()),
        name=name,
        provider_id="1",
        provider_name="seatgeek",
        url="https://example.com",
        image="https://example.com/img.png",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def claim_fields(**overrides) -> dict:
    fields = dict(
        agency_roster_url="https://example.com/roster",
        confirmation_email="artist-confirms@example.com",
        business_email="agent@example.com",
        adder_role="Booking Agent",
        representation="Full representation.",
    )
    fields.update(overrides)
    return fields


class ApiTestCase(TestCase):
    def login_as(self, user) -> None:
        token = RefreshToken.for_user(user).access_token
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"


class ArtistClaimServiceTests(TestCase):
    def setUp(self):
        self.claimant = make_user("agent@example.com")
        self.other_claimant = make_user("other_agent@example.com")
        self.artist_user = make_user("artist@example.com", role="artist")
        self.superuser = make_user("root@example.com", is_superuser=True, is_staff=True)
        self.performer = make_performer("The Roadrunners")

    def test_create_requires_exactly_one_target(self):
        with self.assertRaises(ValidationError):
            ArtistClaimService.create(claimant=self.claimant, **claim_fields())
        with self.assertRaises(ValidationError):
            ArtistClaimService.create(
                claimant=self.claimant,
                artist_user_id=self.artist_user.pk,
                seatgeek_performer_id=self.performer.pk,
                **claim_fields(),
            )

    def test_create_internal_claim_lands_pending(self):
        claim = ArtistClaimService.create(
            claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields(),
        )
        self.assertEqual(claim.status, ClaimStatus.PENDING)
        self.assertEqual(claim.artist_user_id, self.artist_user.pk)
        self.assertIsNone(claim.seatgeek_performer_id)
        self.assertEqual(claim.target_type, "internal")

    def test_create_seatgeek_claim_lands_pending(self):
        claim = ArtistClaimService.create(
            claimant=self.claimant, seatgeek_performer_id=self.performer.pk, **claim_fields(),
        )
        self.assertEqual(claim.status, ClaimStatus.PENDING)
        self.assertEqual(claim.seatgeek_performer_id, self.performer.pk)
        self.assertIsNone(claim.artist_user_id)
        self.assertEqual(claim.target_type, "seatgeek")

    def test_multiple_users_can_claim_the_same_artist(self):
        ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        ArtistClaimService.create(claimant=self.other_claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        self.assertEqual(ArtistClaim.objects.filter(artist_user=self.artist_user).count(), 2)

    def test_same_user_cannot_double_claim_the_same_artist_while_live(self):
        ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        with self.assertRaises(DuplicateClaim):
            ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())

    def test_resubmitting_after_rejection_is_allowed(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        ArtistClaimService.review(reviewer=self.superuser, claim_id=claim.pk, approve=False)
        # Should not raise - the first claim is now rejected (terminal), so
        # the uniqueness constraint no longer blocks a fresh one.
        second = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        self.assertEqual(second.status, ClaimStatus.PENDING)

    def test_review_approves_and_sets_reviewer(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        reviewed = ArtistClaimService.review(reviewer=self.superuser, claim_id=claim.pk, approve=True, note="looks good")
        self.assertEqual(reviewed.status, ClaimStatus.APPROVED)
        self.assertEqual(reviewed.reviewed_by_id, self.superuser.pk)
        self.assertEqual(reviewed.review_note, "looks good")
        self.assertIsNotNone(reviewed.reviewed_at)

    def test_reviewing_twice_is_rejected(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        ArtistClaimService.review(reviewer=self.superuser, claim_id=claim.pk, approve=True)
        with self.assertRaises(AlreadyReviewed):
            ArtistClaimService.review(reviewer=self.superuser, claim_id=claim.pk, approve=True)

    def test_non_owner_cannot_view_someone_elses_claim(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        with self.assertRaises(PermissionDenied):
            ArtistClaimService.get_for_viewer(self.other_claimant, claim.pk)

    def test_admin_can_view_any_claim(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        admin = make_user("admin@example.com", role="admin", is_staff=True)
        fetched = ArtistClaimService.get_for_viewer(admin, claim.pk)
        self.assertEqual(fetched.pk, claim.pk)

    def test_withdraw_deletes_pending_claim(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        ArtistClaimService.withdraw(viewer=self.claimant, claim_id=claim.pk)
        self.assertFalse(ArtistClaim.objects.filter(pk=claim.pk).exists())

    def test_cannot_withdraw_a_reviewed_claim(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        ArtistClaimService.review(reviewer=self.superuser, claim_id=claim.pk, approve=True)
        with self.assertRaises(AlreadyReviewed):
            ArtistClaimService.withdraw(viewer=self.claimant, claim_id=claim.pk)


class ClaimedArtistSearchTests(TestCase):
    def setUp(self):
        self.claimant_a = make_user("agent_a@example.com")
        self.claimant_b = make_user("agent_b@example.com")
        self.artist_user = make_user("famous_artist@example.com", role="artist")
        self.performer = make_performer("The Roadrunners")
        self.superuser = make_user("root@example.com", is_superuser=True, is_staff=True)

    def test_search_groups_multiple_claimants_under_one_artist(self):
        ArtistClaimService.create(claimant=self.claimant_a, artist_user_id=self.artist_user.pk, **claim_fields())
        ArtistClaimService.create(claimant=self.claimant_b, artist_user_id=self.artist_user.pk, **claim_fields())

        rows = ArtistClaimService.search_claimed_artists()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], "internal")
        self.assertEqual(row["artist_user_id"], self.artist_user.pk)
        self.assertEqual(len(row["claimed_by"]), 2)
        claimant_ids = {c["user"]["id"] for c in row["claimed_by"]}
        self.assertEqual(claimant_ids, {self.claimant_a.pk, self.claimant_b.pk})

    def test_search_covers_seatgeek_performers_too(self):
        ArtistClaimService.create(claimant=self.claimant_a, seatgeek_performer_id=self.performer.pk, **claim_fields())

        rows = ArtistClaimService.search_claimed_artists(search="Roadrunners")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "seatgeek")
        self.assertEqual(rows[0]["seatgeek_performer_id"], self.performer.pk)

    def test_search_by_name_filters_correctly(self):
        ArtistClaimService.create(claimant=self.claimant_a, artist_user_id=self.artist_user.pk, **claim_fields())
        self.assertEqual(len(ArtistClaimService.search_claimed_artists(search="famous")), 1)
        self.assertEqual(len(ArtistClaimService.search_claimed_artists(search="nonexistent")), 0)

    def test_unclaimed_artist_never_appears(self):
        # No claims filed at all - the search must return nothing, even
        # though `self.artist_user` and `self.performer` both exist.
        self.assertEqual(ArtistClaimService.search_claimed_artists(), [])

    def test_status_filter_narrows_results(self):
        claim = ArtistClaimService.create(claimant=self.claimant_a, artist_user_id=self.artist_user.pk, **claim_fields())
        ArtistClaimService.review(reviewer=self.superuser, claim_id=claim.pk, approve=True)
        ArtistClaimService.create(claimant=self.claimant_b, seatgeek_performer_id=self.performer.pk, **claim_fields())

        approved_only = ArtistClaimService.search_claimed_artists(status="approved")
        self.assertEqual(len(approved_only), 1)
        self.assertEqual(approved_only[0]["source"], "internal")

        pending_only = ArtistClaimService.search_claimed_artists(status="pending")
        self.assertEqual(len(pending_only), 1)
        self.assertEqual(pending_only[0]["source"], "seatgeek")


class ArtistClaimApiTests(ApiTestCase):
    def setUp(self):
        self.claimant = make_user("agent@example.com")
        self.artist_user = make_user("artist@example.com", role="artist")
        self.superuser = make_user("root@example.com", is_superuser=True, is_staff=True)

    def test_create_claim_via_api(self):
        self.login_as(self.claimant)
        res = self.client.post(
            reverse("artist_claims:claim-list-create"),
            data={"artist_user_id": self.artist_user.pk, **claim_fields()},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["claim"]["status"], "pending")
        self.assertEqual(res.json()["claim"]["artist_user"]["id"], self.artist_user.pk)

    def test_non_admin_cannot_reach_review_queue(self):
        self.login_as(self.claimant)
        res = self.client.get(reverse("artist_claims:claim-review-list"))
        self.assertEqual(res.status_code, 403)

    def test_admin_can_approve_via_api(self):
        claim = ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        self.login_as(self.superuser)
        res = self.client.post(
            reverse("artist_claims:claim-review-detail", args=[claim.pk]),
            data={"approve": True},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["claim"]["status"], "approved")

    def test_search_endpoint_returns_claimants(self):
        ArtistClaimService.create(claimant=self.claimant, artist_user_id=self.artist_user.pk, **claim_fields())
        self.login_as(self.claimant)
        res = self.client.get(reverse("artist_claims:claimed-artist-search"), {"search": "artist"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["results"][0]["claimed_by"]), 1)
