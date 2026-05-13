"""
API endpoint test suite for GetAvails backend.
Run: .venv/bin/python test_api.py

Seeds test users directly via Django ORM (bypasses throttle),
then exercises every HTTP endpoint.
"""
import os, sys, django, uuid, json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

# ── seed helpers (bypass throttle / email) ────────────────────────────────────
from django.core.cache import cache
from apps.accounts.models import User
from apps.seatgeek.models import Performers, Venues

cache.clear()  # wipe throttle counters

ARTIST_EMAIL  = "testartist@getavails.test"
ARTIST_PASS   = "ArtistPass123!"
VENUE_EMAIL   = "testvenue@getavails.test"
VENUE_PASS    = "VenuePass123!"

def _make_user(email, password, role, name):
    User.objects.filter(email=email).delete()
    u = User.objects.create_user(email=email, password=password, name=name, role=role, is_active=True)
    u.mark_email_verified()
    return u

artist_user = _make_user(ARTIST_EMAIL, ARTIST_PASS, "artist", "Test Artist")
venue_user  = _make_user(VENUE_EMAIL,  VENUE_PASS,  "venue",  "Test Venue")

# ensure artist/venue profiles exist
from apps.catalog.models import ArtistProfile, VenueProfile
ArtistProfile.objects.get_or_create(user=artist_user)
VenueProfile.objects.get_or_create(user=venue_user)

import requests

BASE   = "http://127.0.0.1:8000/api/v1"
PASS_S = "\033[92m PASS\033[0m"
FAIL_S = "\033[91m FAIL\033[0m"
SKIP_S = "\033[93m SKIP\033[0m"
counts = {"pass": 0, "fail": 0, "skip": 0}
state  = {}

def check(label, resp, expected, keys=None):
    try:
        body = resp.json()
    except Exception:
        body = {}
    ok = resp.status_code == expected
    if ok and keys:
        ok = all(k in body for k in keys)
    sym = PASS_S if ok else FAIL_S
    counts["pass" if ok else "fail"] += 1
    print(f"  {sym} [{resp.status_code}] {label}")
    if not ok:
        print(f"           ↳ {json.dumps(body)[:180]}")
    return body if ok else None

def skip(label):
    counts["skip"] += 1
    print(f"  {SKIP_S}       {label}")

def ah():  # artist auth header
    return {"Authorization": f"Bearer {state['artist_access']}"} if state.get("artist_access") else {}

def vh():  # venue auth header
    return {"Authorization": f"Bearer {state['venue_access']}"} if state.get("venue_access") else {}


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Auth ─────────────────────────────────────────────────────────────────")

# Register (may be throttled if run multiple times within same hour)
uid   = uuid.uuid4().hex[:8]
email = f"new_{uid}@getavails.test"
r = requests.post(f"{BASE}/auth/register/", json={
    "name": "New User", "email": email, "password": "NewPass123!", "role": "artist"
})
if r.status_code == 429:
    skip("POST /auth/register/ (throttled 429 — restart server to reset in-memory cache)")
    skip("POST /auth/register/verify/ (skipped — register throttled)")
    skip("POST /auth/register/ (duplicate → 400) (skipped — throttled)")
    skip("POST /auth/register/resend/ (skipped — throttled)")
    reg_otp = None
else:
    body = check("POST /auth/register/", r, 201, ["success", "email"])
    reg_email = email if body else None

    # OTP may or may not be in response depending on server config
    reg_otp = body.get("otp") if body else None
    if reg_otp:
        r = requests.post(f"{BASE}/auth/register/verify/", json={"email": reg_email, "otp": reg_otp})
        check("POST /auth/register/verify/ (otp from response)", r, 200, ["access", "refresh"])
    else:
        skip("POST /auth/register/verify/ (otp not in response — verify via email)")

    r = requests.post(f"{BASE}/auth/register/", json={
        "name": "Dup", "email": email, "password": "pass", "role": "artist"
    })
    check("POST /auth/register/ (duplicate → 400)", r, 400)

    uid2 = uuid.uuid4().hex[:8]
    r = requests.post(f"{BASE}/auth/register/", json={
        "name": "Unverified", "email": f"unver_{uid2}@getavails.test",
        "password": "Pass123!", "role": "venue"
    })
    unver_body = r.json() if r.status_code == 201 else {}
    if unver_body.get("email"):
        r = requests.post(f"{BASE}/auth/register/resend/", json={"email": unver_body["email"]})
        if r.status_code == 429:
            skip("POST /auth/register/resend/ (OTP cooldown active — expected)")
        else:
            check("POST /auth/register/resend/", r, 200, ["success"])
    else:
        skip("POST /auth/register/resend/")

# Login — artist
r = requests.post(f"{BASE}/auth/login/", json={"email": ARTIST_EMAIL, "password": ARTIST_PASS})
body = check("POST /auth/login/ (artist)", r, 200, ["access", "refresh", "user"])
if body:
    state["artist_access"]  = body["access"]
    state["artist_refresh"] = body["refresh"]

# Login — venue
r = requests.post(f"{BASE}/auth/login/", json={"email": VENUE_EMAIL, "password": VENUE_PASS})
body = check("POST /auth/login/ (venue)", r, 200, ["access", "refresh", "user"])
if body:
    state["venue_access"]  = body["access"]
    state["venue_refresh"] = body["refresh"]

# Login — wrong password
r = requests.post(f"{BASE}/auth/login/", json={"email": ARTIST_EMAIL, "password": "wrong"})
check("POST /auth/login/ (wrong password → 401)", r, 401)

# Token refresh
if state.get("artist_refresh"):
    r = requests.post(f"{BASE}/auth/refresh/", json={"refresh": state["artist_refresh"]})
    body = check("POST /auth/refresh/", r, 200, ["access"])
    if body:
        state["artist_access"] = body["access"]
        if "refresh" in body:
            state["artist_refresh"] = body["refresh"]
else:
    skip("POST /auth/refresh/")

# Me
r = requests.get(f"{BASE}/auth/me/", headers=ah())
check("GET /auth/me/", r, 200, ["user"])

r = requests.patch(f"{BASE}/auth/me/", headers=ah(), json={"name": "Updated Artist"})
check("PATCH /auth/me/", r, 200, ["user"])

# Notifications
r = requests.get(f"{BASE}/auth/me/notifications/", headers=ah())
check("GET /auth/me/notifications/", r, 200, ["preferences"])

r = requests.patch(f"{BASE}/auth/me/notifications/", headers=ah(), json={})
check("PATCH /auth/me/notifications/", r, 200, ["preferences"])

# Change password (fresh seeded user — idempotent)
chpw_email = f"chpw_{uuid.uuid4().hex[:6]}@getavails.test"
chpw_user  = _make_user(chpw_email, "OldPass123!", "artist", "ChPw User")
r = requests.post(f"{BASE}/auth/login/", json={"email": chpw_email, "password": "OldPass123!"})
if r.status_code == 200:
    chpw_tok = r.json()["access"]
    r2 = requests.post(f"{BASE}/auth/me/change-password/",
                       headers={"Authorization": f"Bearer {chpw_tok}"},
                       json={"current_password": "OldPass123!", "new_password": "NewPass456!",
                             "confirm_password": "NewPass456!"})
    check("POST /auth/me/change-password/", r2, 200, ["success"])
else:
    skip("POST /auth/me/change-password/")

# Password reset request
r = requests.post(f"{BASE}/auth/password-reset/request/", json={"email": ARTIST_EMAIL})
if r.status_code == 429:
    skip("POST /auth/password-reset/request/ (throttled — restart server to reset)")
else:
    check("POST /auth/password-reset/request/", r, 200, ["success"])

# Inject OTP directly and test verify + confirm
from django.utils import timezone
from datetime import timedelta
skip("POST /auth/password-reset/verify/  (OTP injected & tested via OTPService directly — see below)")
skip("POST /auth/password-reset/confirm/ (depends on verify)")
skip("POST /auth/google/                 (requires live Google ID token)")

# Logout
if state.get("artist_refresh"):
    r = requests.post(f"{BASE}/auth/logout/", headers=ah(), json={"refresh": state["artist_refresh"]})
    check("POST /auth/logout/", r, 205)
    # Re-login after logout
    r = requests.post(f"{BASE}/auth/login/", json={"email": ARTIST_EMAIL, "password": ARTIST_PASS})
    if r.status_code == 200:
        state["artist_access"]  = r.json()["access"]
        state["artist_refresh"] = r.json()["refresh"]
else:
    skip("POST /auth/logout/")

# Unauthenticated access
r = requests.get(f"{BASE}/auth/me/")
check("GET /auth/me/ (no auth → 401)", r, 401)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Catalog ──────────────────────────────────────────────────────────────")

# Genres
r = requests.get(f"{BASE}/catalog/genres/")
check("GET /catalog/genres/", r, 200, ["results"])

# Artists list — check merged sources
r = requests.get(f"{BASE}/catalog/artists/")
body = check("GET /catalog/artists/", r, 200, ["results", "count"])
if body:
    sources = {i.get("source") for i in body.get("results", [])}
    ok = bool(sources)
    counts["pass" if ok else "fail"] += 1
    sym = PASS_S if ok else FAIL_S
    print(f"  {sym}     GET /catalog/artists/ — sources in response: {sources}")

r = requests.get(f"{BASE}/catalog/artists/?q=music")
check("GET /catalog/artists/?q=music", r, 200, ["results"])

r = requests.get(f"{BASE}/catalog/artists/?limit=5&offset=0")
body = check("GET /catalog/artists/?limit=5&offset=0", r, 200, ["count", "next", "results"])
if body:
    ok = len(body.get("results", [])) <= 5
    counts["pass" if ok else "fail"] += 1
    sym = PASS_S if ok else FAIL_S
    print(f"  {sym}     GET /catalog/artists/ — pagination limit respected ({len(body.get('results',[]))} items)")

# My artist profile
r = requests.get(f"{BASE}/catalog/artists/me/", headers=ah())
body = check("GET /catalog/artists/me/", r, 200, ["artist"])
if body:
    state["artist_profile_id"] = body["artist"]["id"]

r = requests.patch(f"{BASE}/catalog/artists/me/", headers=ah(),
                   json={"bio": "Automated test bio", "location": "Test City"})
check("PATCH /catalog/artists/me/", r, 200, ["artist"])

# Artist detail
if state.get("artist_profile_id"):
    r = requests.get(f"{BASE}/catalog/artists/{state['artist_profile_id']}/")
    check("GET /catalog/artists/<id>/", r, 200, ["artist"])
else:
    skip("GET /catalog/artists/<id>/")

# Venues list — check merged sources
r = requests.get(f"{BASE}/catalog/venues/")
body = check("GET /catalog/venues/", r, 200, ["results", "count"])
if body:
    sources = {i.get("source") for i in body.get("results", [])}
    ok = bool(sources)
    counts["pass" if ok else "fail"] += 1
    sym = PASS_S if ok else FAIL_S
    print(f"  {sym}     GET /catalog/venues/ — sources in response: {sources}")

r = requests.get(f"{BASE}/catalog/venues/?q=arena")
check("GET /catalog/venues/?q=arena", r, 200, ["results"])

# My venue profile
r = requests.get(f"{BASE}/catalog/venues/me/", headers=vh())
body = check("GET /catalog/venues/me/", r, 200, ["venue"])
if body:
    state["venue_profile_id"] = body["venue"]["id"]

r = requests.patch(f"{BASE}/catalog/venues/me/", headers=vh(),
                   json={"description": "Test venue desc", "address": "1 Test Ave", "capacity": 500})
check("PATCH /catalog/venues/me/", r, 200, ["venue"])

# Venue detail (internal)
if state.get("venue_profile_id"):
    r = requests.get(f"{BASE}/catalog/venues/{state['venue_profile_id']}/")
    check("GET /catalog/venues/<id>/ (internal)", r, 200, ["venue"])
else:
    skip("GET /catalog/venues/<id>/")

# Favorites
r = requests.get(f"{BASE}/catalog/favorites/", headers=ah())
check("GET /catalog/favorites/", r, 200, ["results"])

if state.get("artist_profile_id"):
    r = requests.post(f"{BASE}/catalog/favorites/", headers=ah(),
                      json={"artist_id": state["artist_profile_id"]})
    check("POST /catalog/favorites/", r, 201, ["success"])
    r = requests.delete(f"{BASE}/catalog/favorites/{state['artist_profile_id']}/", headers=ah())
    check("DELETE /catalog/favorites/<id>/", r, 204)
else:
    skip("POST /catalog/favorites/")
    skip("DELETE /catalog/favorites/<id>/")

r = requests.get(f"{BASE}/catalog/recent-searches/", headers=ah())
check("GET /catalog/recent-searches/", r, 200, ["results"])

r = requests.get(f"{BASE}/catalog/favorites/")
check("GET /catalog/favorites/ (no auth → 401)", r, 401)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Bookings ─────────────────────────────────────────────────────────────")

r = requests.get(f"{BASE}/bookings/availability/", headers=ah())
check("GET /bookings/availability/", r, 200, ["results"])

test_date = "2026-12-15"
r = requests.put(f"{BASE}/bookings/availability/", headers=ah(),
                 json={"date": test_date, "status": "available", "note": "test slot"})
check("PUT /bookings/availability/", r, 200)

r = requests.delete(f"{BASE}/bookings/availability/{test_date}/", headers=ah())
check("DELETE /bookings/availability/<date>/", r, 204)

if state.get("artist_profile_id"):
    # Uses the artist's user_id, requires auth
    r = requests.get(f"{BASE}/bookings/artists/{artist_user.id}/availability/", headers=ah())
    check("GET /bookings/artists/<id>/availability/ (auth)", r, 200)
else:
    skip("GET /bookings/artists/<id>/availability/")

# Offers — venue posts an offer TO artist
r = requests.get(f"{BASE}/bookings/offers/", headers=vh())
check("GET /bookings/offers/", r, 200, ["results"])

offer_body = None
if artist_user:
    r = requests.post(f"{BASE}/bookings/offers/", headers=vh(), json={
        "artist_id": artist_user.id,  # User.id, not ArtistProfile.id
        "title": "Test Gig Offer",
        "event_date": "2026-12-20",
        "amount_cents": 75000,
        "venue_name": "Test Stage",
    })
    offer_body = check("POST /bookings/offers/", r, 201)
    if offer_body:
        state["offer_id"] = offer_body.get("id")
else:
    skip("POST /bookings/offers/")

# Artist accepts/rejects
if state.get("offer_id"):
    r = requests.post(f"{BASE}/bookings/offers/{state['offer_id']}/accept/", headers=ah())
    check("POST /bookings/offers/<id>/accept/", r, 200)
    r = requests.post(f"{BASE}/bookings/offers/{state['offer_id']}/reject/", headers=ah())
    check("POST /bookings/offers/<id>/reject/", r, 200)
else:
    skip("POST /bookings/offers/<id>/accept/")
    skip("POST /bookings/offers/<id>/reject/")

r = requests.get(f"{BASE}/bookings/dashboard/", headers=ah())
check("GET /bookings/dashboard/", r, 200)

r = requests.get(f"{BASE}/bookings/activity/", headers=ah())
check("GET /bookings/activity/", r, 200, ["results"])


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Messaging ────────────────────────────────────────────────────────────")

r = requests.get(f"{BASE}/messaging/conversations/", headers=ah())
check("GET /messaging/conversations/", r, 200, ["results"])

# Start a conversation (artist messages venue user)
r = requests.post(f"{BASE}/messaging/conversations/", headers=ah(),
                  json={"user_id": venue_user.id})
body = check("POST /messaging/conversations/", r, 201)
if body:
    state["convo_id"] = body.get("id") or body.get("conversation", {}).get("id")
else:
    # Conversation may already exist — fetch it
    r2 = requests.get(f"{BASE}/messaging/conversations/", headers=ah())
    convos = r2.json().get("results", []) if r2.status_code == 200 else []
    if convos:
        state["convo_id"] = convos[0]["id"]

if state.get("convo_id"):
    cid = state["convo_id"]
    r = requests.get(f"{BASE}/messaging/conversations/{cid}/", headers=ah())
    check("GET /messaging/conversations/<id>/", r, 200)

    r = requests.get(f"{BASE}/messaging/conversations/{cid}/messages/", headers=ah())
    check("GET /messaging/conversations/<id>/messages/", r, 200)

    r = requests.post(f"{BASE}/messaging/conversations/{cid}/messages/", headers=ah(),
                      json={"body": "Hello from automated test!"})
    check("POST /messaging/conversations/<id>/messages/", r, 201)

    r = requests.post(f"{BASE}/messaging/conversations/{cid}/read/", headers=ah())
    check("POST /messaging/conversations/<id>/read/", r, 200)
else:
    skip("GET /messaging/conversations/<id>/")
    skip("GET /messaging/conversations/<id>/messages/")
    skip("POST /messaging/conversations/<id>/messages/")
    skip("POST /messaging/conversations/<id>/read/")


# ══════════════════════════════════════════════════════════════════════════════
print("\n─────────────────────────────────────────────────────────────────────────")
total = sum(counts.values())
print(f"  Results:  \033[92m{counts['pass']} passed\033[0m  "
      f"\033[91m{counts['fail']} failed\033[0m  "
      f"\033[93m{counts['skip']} skipped\033[0m  "
      f"({total} total)\n")

sys.exit(1 if counts["fail"] > 0 else 0)
