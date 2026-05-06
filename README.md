# GetAvails Backend

Production-grade Django REST Framework backend for the **GetAvails / ArtistBook** platform. Implements the full client-side authentication flow shown in the UI: email + password sign-up with role selection, 6-digit OTP email verification, JWT login, Google sign-in for existing accounts, and OTP-based password reset.

---

## Tech stack

| Layer | Choice |
|---|---|
| Runtime | Python 3.12 |
| Framework | Django 5.x + Django REST Framework |
| Auth | `djangorestframework-simplejwt` (access + refresh, blacklist on rotation) |
| OAuth | `google-auth` (verifies Google ID tokens server-side; SPA pattern) |
| DB (dev) | SQLite |
| DB (prod) | PostgreSQL 16 |
| Cache / throttling | Redis 7 (prod) / locmem (dev) |
| Web server | Gunicorn behind Nginx |
| Container | Docker + Docker Compose |
| Config | `django-environ` (`.env`) |
| Layout | Layered: `views (APIView) → services → models` |

Generic / model viewsets are intentionally not used; every endpoint is a class-based `APIView` with business logic delegated to a service class.

---

## Project structure

```
GetAvails_Backend/
├── manage.py
├── gunicorn.conf.py
├── Dockerfile
├── docker-compose.yml
├── nginx/default.conf
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── .env.example
├── config/
│   ├── settings/
│   │   ├── base.py        # shared settings, DRF + JWT + OTP config
│   │   ├── dev.py         # SQLite, locmem cache, console email, CORS open
│   │   └── prod.py        # Postgres, Redis, SMTP, security headers
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
└── apps/
    ├── common/
    │   ├── models.py        # TimeStampedModel
    │   └── exceptions.py    # consistent {success, error: {code,...}} envelope
    └── accounts/
        ├── models.py        # User, EmailOTP
        ├── managers.py      # UserManager
        ├── serializers.py
        ├── services.py      # AuthService, RegistrationService, OTPService,
        │                    # PasswordResetService, GoogleAuthService
        ├── tokens.py        # signed reset token (auto-invalidates on pwd change)
        ├── emails.py        # OTP email content
        ├── exceptions.py    # EmailNotVerified, GoogleAccountNotFound, ...
        ├── permissions.py   # IsActiveStaff, HasRole
        ├── throttling.py    # per-flow scoped throttles
        ├── views.py         # all APIView classes
        ├── urls.py
        ├── admin.py
        └── management/commands/create_admin.py
```

---

## Local development

Prerequisites: Python 3.12, `pip`.

```powershell
# 1. Create venv and install dev deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements/dev.txt

# 2. Copy env template
copy .env.example .env

# 3. Migrate and create an admin (will prompt for password)
python manage.py makemigrations accounts
python manage.py migrate
python manage.py create_admin --email admin@getavails.com --name "Admin" --superuser

# 4. Run the dev server
python manage.py runserver
```

In dev, emails are printed to the console (no SMTP needed) — copy the OTP from the terminal when testing the flow.

---

## API reference

All endpoints are versioned under `/api/v1/auth/`. Successful responses follow `{"success": true, ...}`; errors follow:

```json
{
  "success": false,
  "error": {
    "code": "email_not_verified",
    "status": 403,
    "message": "Please verify your email before logging in.",
    "details": { ... }
  }
}
```

The `error.code` field is stable and the frontend should route on it.

### Sign Up flow

#### `POST /api/v1/auth/register/`

```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "password": "S3cure!Pass",
  "role": "artist"
}
```

`role` ∈ `artist | agent | talent_buyer | venue | organizer`.

**201 Created**
```json
{
  "success": true,
  "message": "Account created. Check your email for a 6-digit verification code.",
  "email": "jane@example.com"
}
```

#### `POST /api/v1/auth/register/verify/`

```json
{ "email": "jane@example.com", "otp": "123456" }
```

**200 OK** — issues JWTs; this is when the frontend can navigate to "You're all set!".
```json
{
  "success": true,
  "message": "Email verified.",
  "user": { "id": 1, "email": "...", "name": "...", "role": "artist", ... },
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

#### `POST /api/v1/auth/register/resend/`

```json
{ "email": "jane@example.com" }
```
Always responds 200 OK with a generic message (does not leak whether the address is registered). 60-second resend cooldown enforced server-side.

### Sign In

#### `POST /api/v1/auth/login/`

```json
{ "email": "jane@example.com", "password": "S3cure!Pass", "remember_me": true }
```

`remember_me=true` extends the refresh token TTL to `JWT_REMEMBER_ME_REFRESH_TTL_DAYS` (default 30) instead of the default 1 day.

**200 OK**
```json
{
  "success": true,
  "user": { ... },
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

**403 — unverified email** (frontend should route to the OTP screen):
```json
{
  "success": false,
  "error": { "code": "email_not_verified", "status": 403, "message": "...", "details": {"detail": "..."} }
}
```

#### `POST /api/v1/auth/google/` — Google sign-in (existing accounts only)

The frontend handles the Google popup/redirect itself, then sends the resulting **ID token** here.

```json
{ "id_token": "<google-id-token-jwt>" }
```

**200 OK** — same shape as `/login/`.

**404 — no account exists for this Google identity**:
```json
{
  "success": false,
  "error": {
    "code": "account_not_found",
    "status": 404,
    "message": "No account found for this Google identity. Please sign up first.",
    "details": {"detail": "..."}
  }
}
```
Frontend should redirect to the Sign Up screen.

If the email already has a password account but no linked Google identity, the Google `sub` is auto-linked on first successful Google login (and `email_verified_at` is set).

### Tokens

#### `POST /api/v1/auth/refresh/`
```json
{ "refresh": "<jwt>" }
```
Returns a new `access` (and `refresh`, since refresh-rotation is enabled).

#### `POST /api/v1/auth/logout/` — *requires `Authorization: Bearer <access>`*
```json
{ "refresh": "<jwt>" }
```
Blacklists the refresh token. **205 Reset Content** on success.

#### `GET /api/v1/auth/me/` — *requires bearer auth*
Returns the current user.

### Password reset flow

```
POST /password-reset/request/   { email }                   → 200 (always; doesn't leak)
POST /password-reset/verify/    { email, otp }              → 200 { reset_token }
POST /password-reset/confirm/   { reset_token, new_password, confirm_password } → 200
```

The `reset_token` is a signed, 10-minute, single-use token that embeds a fingerprint of the password hash — it is automatically invalidated the moment the password changes. On successful reset, **all outstanding refresh tokens for the user are blacklisted** (forces re-login on every device).

---

## Auth flow assumptions (locked in)

These were confirmed against the UI; documented here so anyone reading the code can verify intent.

1. **Roles are fixed** at `artist | agent | talent_buyer | venue | organizer` (enum on `User.role`).
2. **Sign up requires email verification.** New accounts have `email_verified_at = NULL`. Login is blocked (`403 email_not_verified`) until OTP is verified.
3. **Google sign-in does not create accounts.** Unknown identities return `404 account_not_found`. Existing email accounts are auto-linked on first success.
4. **No public username/handle.** Email is the unique identifier (`USERNAME_FIELD = "email"`).
5. **OTP**: 6 digits, 10-min TTL, max 5 attempts, hashed at rest (sha-256), single-use, 60-second resend cooldown. The `EmailOTP` table has a `purpose` enum so signup verification and password reset share the same machinery.
6. **Tokens revoked on password change.** All `OutstandingToken`s for the user are blacklisted in the same transaction as the password update.
7. **Password rules** follow Django's built-in validators: min length 8, not too similar to user attributes, not in the common-password list, not all-numeric.
8. **Settings split** by environment (`base / dev / prod`). Dev defaults to SQLite + console email so the project runs with zero external services.

---

## Production deployment (Hostinger VPS)

The provided Compose file runs the full stack: `web` (Gunicorn) + `db` (Postgres) + `redis` + `nginx`.

```bash
# On the VPS
git clone <repo> getavails && cd getavails
cp .env.example .env
# edit .env: set DJANGO_SECRET_KEY, DJANGO_DEBUG=False, ALLOWED_HOSTS, DATABASE_URL,
#           REDIS_URL, EMAIL_* (real SMTP), GOOGLE_OAUTH_CLIENT_ID, FRONTEND_URL,
#           CORS_ALLOWED_ORIGINS, DJANGO_SETTINGS_MODULE=config.settings.prod

docker compose up -d --build
docker compose exec web python manage.py create_admin \
    --email admin@yourdomain.com --name "Admin" --superuser
```

**Recommended once HTTPS is set up at the edge (e.g., via Nginx Proxy Manager or a separate Caddy/Traefik):**
- Set `DJANGO_SECURE_SSL_REDIRECT=True` in `.env`.
- Trust the proxy header with `SECURE_PROXY_SSL_HEADER` (already configured in `prod.py`).
- Issue Let's Encrypt certificates outside the app container.

### Storage

- **Static**: collected to `/app/staticfiles`, served by Nginx from the `static_data` volume.
- **Media** (avatars): written to `/app/media`, served by Nginx from the `media_data` volume. Swap path to S3-compatible storage later by replacing `DEFAULT_FILE_STORAGE`.
- **Logs**: written to `/app/logs/app.log` (rotating, 10 MB × 5).

### Performance / scalability notes

- DRF throttles share state via Redis cache in prod (`REST_FRAMEWORK.DEFAULT_THROTTLE_CACHE = "default"`), so rate limits hold across all Gunicorn workers.
- Gunicorn defaults: `workers = (2 × CPU + 1)`, `threads = 4`, `max_requests = 1000` with jitter (workers recycle to bound memory growth).
- Postgres connection pooling enabled via `CONN_MAX_AGE = 60`.
- Indexes on `users.email`, `users.role`, `email_otps (user, purpose, -created_at)`, `email_otps.expires_at`.
- All query paths in services are O(1)/O(log n) — no list-views yet, but when added, use `select_related` / `prefetch_related` and DRF pagination.

---

## Operations

### Useful management commands

```bash
python manage.py create_admin --email a@b.com --name "Admin" --role organizer --superuser
python manage.py changepassword <email>
python manage.py flushexpiredtokens   # simplejwt: clean blacklisted refresh tokens
```

### Testing the flow with curl

```bash
BASE=http://localhost:8000/api/v1/auth

# sign up
curl -X POST $BASE/register/ -H "Content-Type: application/json" \
  -d '{"name":"Jane","email":"jane@example.com","password":"S3cure!Pass","role":"artist"}'

# (read OTP from runserver console output — dev uses console email backend)
curl -X POST $BASE/register/verify/ -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","otp":"123456"}'

# login
curl -X POST $BASE/login/ -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"S3cure!Pass","remember_me":true}'

# me
curl $BASE/me/ -H "Authorization: Bearer $ACCESS"
```

---

## License

Internal — GetAvails team.
