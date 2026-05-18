# GetAvails Backend

Django + DRF API for **ArtistBook** — an artist-booking platform. Frontends use these endpoints; there is no server-rendered UI here.

## Stack

- Python 3.10, Django 5.1, DRF 3.15, SimpleJWT 5.5
- PostgreSQL 16 (psycopg 3) — **never SQLite, even for tests/dev**
- Redis (prod-only cache + throttle store)
- Settings split: `config/settings/{base,dev,prod}.py`. `manage.py` defaults to `config.settings.dev`. Config via `django-environ` reading `.env`.

## Hard rules

- **APIView only.** Every DRF endpoint must subclass `rest_framework.views.APIView` directly. Do not use `GenericAPIView`, `ViewSet`, `ModelViewSet`, or any of their mixins. Pagination is opt-in per-view by setting `pagination_class = StandardPagination` and calling it explicitly (see `apps/bookings/views.py` for the pattern).
- **No emojis in code or files** unless explicitly requested.
- **Don't create docs/READMEs** unless explicitly requested.

## Project layout

```
apps/
  accounts/    # User, OTP, JWT auth, Google sign-in, password reset
  catalog/     # ArtistProfile, VenueProfile, Genre, Favorites, RecentSearch, unified artist+SG search
  bookings/    # AvailabilitySlot, BookingOffer, dashboard, activity feed
  messaging/   # In-app messaging
  seatgeek/    # External-data mirror (Performers, Events, Venues, PerformerEvents). Populated by a scraper outside this repo.
  common/      # TimeStampedModel, StandardPagination, exception handler
config/
  settings/    # base / dev / prod
  urls.py      # Mounts /api/v1/{auth,catalog,bookings,messaging}/
```

All app models inherit `apps.common.models.TimeStampedModel` (`created_at` + `updated_at`).

## URL prefixes

All endpoints live under `/api/v1/`:
- `/api/v1/auth/` — accounts app
- `/api/v1/catalog/` — artists, venues, genres, favorites, recent searches
- `/api/v1/bookings/` — availability slots, offers, dashboard, activity
- `/api/v1/messaging/` — threads + messages

## Response envelope

Every response goes through `apps.common.exceptions.api_exception_handler` and shares this shape:

- Success: `{"success": true, ...payload}` (set explicitly in the view's `Response(...)`)
- Error: `{"success": false, "error": {"code": "...", "status": 4xx, "message": "...", "details": {...}}}`
- Paginated lists: `StandardPagination` returns `{"success": true, "count", "limit", "offset", "next", "previous", "results": [...]}`. Default limit 20, max 100. LimitOffset-based.

Frontend routes errors on `error.code`, so when raising DRF exceptions prefer custom `default_code` over relying on `message`.

## Auth

- JWT via SimpleJWT. `AUTH_HEADER_TYPES = ("Bearer",)`. Access token TTL is 15 min, refresh rotates.
- Custom user: `accounts.User` (email-based, no username). Roles: `artist`, `agent`, `talent_buyer`, `venue`, `organizer`.
- Signup flow uses 6-digit email OTP. Google sign-in is **login-only for existing accounts**, not a registration path.

## SeatGeek data (important)

The `seatgeek` app mirrors an external dataset. Tables (`events`, `performers`, `venues`, `performer_events`, `performer_genres`, etc.) are populated by a separate scraper — **don't write to them from API code**; treat them as read-only.

Key shape:
- `Performers` has no location field. Only `Events` and `Venues` do.
- `Events` has `start_date` + `end_date` (DateFields). Multi-day events span the full range; any availability filter must use the overlap predicate `start_date <= to AND end_date >= from`.
- `PerformerEvents` links the two (M2M-as-table).
- PKs are `CharField(max_length=191)` — opaque external IDs, not ints.

The artist search endpoint (`/api/v1/catalog/artists/`) **merges internal `ArtistProfile`s with SG `Performers`** in a single paginated response. Each row carries `"source": "internal" | "seatgeek"`. Both sources expose the same availability fields:
- `booked_dates`: list of `{start_date, end_date, weekday, ...}` over the next 365 days.
- `available_ranges`: complementary free-range list over the same window.

`AVAILABILITY_WINDOW_DAYS = 365` is the shared constant (defined in both `services.py` and `serializers.py`).

## Availability domain

Two distinct storage shapes share one search API:

| Source | Storage | "Booked" means |
|---|---|---|
| Internal artist | `bookings.AvailabilitySlot(user, date, status)` per day | `status` is `BOOKED` or `SOFT_HOLD` |
| SeatGeek performer | `seatgeek.Events` linked via `PerformerEvents` | any event range overlaps the query window |

Search-by-date supports either form:
- `?available_on=YYYY-MM-DD` — single day
- `?available_from=...&available_to=...` — range
- `?available_on=X&available_to=Y` — `available_on` is treated as the start; the helper `_resolve_availability_range` in `apps/catalog/services.py` normalizes any combination (including reversed ranges).

Geo filter (`latitude`/`longitude`/`radius_miles`) currently applies to **internal artists only** — SG performers have no own location. See `_bounding_box` + `_haversine_miles` for the two-stage filter.

## Service / serializer / view split

Business logic lives in `<app>/services.py` as `*Service` classes with `@staticmethod` methods. Views are thin: parse → call service → serialize → respond. Don't put query logic or domain rules in views or serializers.

Heavy reads use `select_related` / `prefetch_related` (often via a custom `Prefetch(..., to_attr=...)` so serializer methods can read the prefetched cache without re-querying). See `_prefetch_upcoming_slots` in `apps/catalog/services.py` for the pattern.

## Tests

- Location: `apps/<app>/tests/test_*.py` (each `tests/` is a package — drop an empty `__init__.py`).
- Use Django `TestCase` (transaction-wrapped) and `Client` / `force_login`. Reverse URLs via `reverse("<namespace>:<name>")`.
- Run: `python manage.py test apps.<app>` — Django auto-creates a `test_<dbname>` Postgres database, so a reachable Postgres is required.
- For new SG-side fixtures, remember PKs are strings: `id=str(uuid.uuid4())` and `created_at`/`updated_at` are non-nullable on the external models.

## Dev workflow

- Local Postgres expected on whatever `DATABASE_URL` in `.env` points to (compose default: `db:5432` — only reachable from inside the compose network). Override `DATABASE_URL` to a host-reachable Postgres when running tests from the host shell.
- `python manage.py check` is the cheapest sanity gate and works without a DB connection if you point `DATABASE_URL` at sqlite temporarily — but **do not commit code that switched the project to SQLite**.
- Migrations: when adding indexes/constraints on `seatgeek` tables, generate a new migration file in `apps/seatgeek/migrations/` even though the external scraper owns the data — Django still manages the schema.

## Things to know that aren't obvious from the code

- `Performers` table can have ~1000s of rows. The list endpoint counts both sources (`internal_qs.count() + sg_qs.count()`) and concatenates — internal first, SG filling the rest of the page. Don't reorder unless you also adjust the pagination math.
- `favorites_only=true` only makes sense for internal artists; the view must short-circuit and *not* call `SeatGeekService.search_performers` when set, otherwise SG rows leak through.
- `genres` filter must apply to **both** sources. SG genre storage is free-text on `PerformerGenres.genre`, so match case-insensitively (`iexact` + `icontains`).
