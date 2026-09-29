# New Features - Frontend Summary

Short reference for everything added recently. All endpoints are under `/api/v1/`,
same response envelope as always (`{"success": true, ...}` / error shape unchanged).

---

## 1. Two new team roles

`Supervisor` and `Mini Super Admin` added to both Artist and Venue role hierarchies
(lowest/most-junior ranks). Show up automatically wherever roles are listed:

`GET /api/v1/teams/roles/?domain=artist`
```json
{ "role": "artist_supervisor", "label": "Supervisor", "rank": 7 }
{ "role": "artist_mini_super_admin", "label": "Mini Super Admin", "rank": 8 }
```
Nothing else changed - existing roles, ranks, and add/invite flows are untouched.

---

## 2. User search now matches phone too

All "search users" endpoints (`teams` related/public user search, `messaging`
user search, `bookings` send-to-users) now match `phone` in addition to
`name`/`email`. Same `?search=` param, no request/response shape change.

---

## 3. Artist role no longer requires extra fields (toggle, not removed)

Adding/inviting someone as `artist` to a team used to require
`agency_roster_url`, `confirmation_email`, `business_email`, `adder_role`,
`representation`. **That's now off** - artist is added exactly like any other
role, no extra fields, no `details` payload needed. The code still exists
(single flag `ARTIST_ROLE_REQUIRES_DETAILS` in `apps/teams/roles.py`) and can
be turned back on later without a frontend change.

---

## 4. Team auto group chat

Every team gets **one auto-managed group chat**. Members are added/removed
automatically as their `TeamMembership` gets approved/removed - no manual
add/remove/leave, and calling those endpoints on a team's group now returns
`400`.

**Open it from a team page:**
```
GET /api/v1/messaging/conversations/team/{team_id}/
```
```json
{ "success": true, "conversation": { "id": 42, "is_group": true, "...": "..." } }
```
`404` = no group yet (nobody approved into the team yet) or you're not an
approved member of that team.

---

## 5. Messages now have a `kind`: text / offer / system

Every message object has a new `kind` field. Old `text` messages are
unaffected - this is purely additive. Full field-by-field reference with all
JSON shapes: see **`CHAT_OFFERS_INTEGRATION.md`** in the repo root. Quick
summary:

| kind | What it means | Render as |
|---|---|---|
| `text` | normal message (unchanged) | chat bubble |
| `offer` | a booking offer sent into a DM | preview card (`message.offer`) |
| `system` | membership event (join/add/remove/leave) | centered system line (`message.system_event`) |

### 5a. Offers in chat
`POST /api/v1/offers/` - same flow, fields, validation as before. New
**optional** field: `conversation_id`. If given (must be a DM you're in, and
its other participant must be the offer's receiver), the offer also gets
posted as a `kind: "offer"` message. Tapping the card opens the existing
offer detail screen (`GET /api/v1/offers/{id}/`) - unchanged.

### 5b. System messages
Fire automatically on: member added, member removed, someone leaving, a team
member's approval (`member_joined`), a team member's removal
(`member_removed_from_team`). No action needed from frontend beyond
rendering `kind: "system"` messages as a system line using `body` or
`system_event`.

---

## 6. Artist Claims (new, independent app)

Any user can claim they represent an artist - either an internal platform
user or a SeatGeek performer. Multiple people can claim the same artist.
Completely separate from team membership (claiming does **not** add anyone to
a team). Needs superadmin review, same as team memberships.

Base path: `/api/v1/artist-claims/`

| Endpoint | Purpose |
|---|---|
| `POST /` | File a claim (`artist_user_id` **or** `seatgeek_performer_id` + proof fields) |
| `GET /` | My own claims |
| `GET /{id}/` | View one claim |
| `DELETE /{id}/` | Withdraw (only while `pending`) |
| `GET /search/?search=&status=` | Search **claimed** artists - see below |
| `GET /review/`, `POST /review/{id}/` | Superadmin queue (approve/reject) |

**Search response** - one row per distinct claimed artist, with every
claimant listed:
```json
{
  "success": true,
  "count": 1,
  "results": [
    {
      "source": "internal",
      "artist_user_id": 12,
      "seatgeek_performer_id": null,
      "name": "Famous Artist",
      "image": "https://backend.getavails.com/media/avatars/xyz.jpg",
      "claimed_by": [
        {
          "claim_id": 5,
          "user": { "id": 3, "name": "Agent A", "email": "agent@example.com" },
          "status": "approved",
          "claimed_at": "2026-09-20T10:00:00Z"
        }
      ]
    }
  ]
}
```
- `source` is `"internal"` or `"seatgeek"` - only one of `artist_user_id` /
  `seatgeek_performer_id` is set accordingly.
- `image` resolves from `User.image` (internal) or `Performers.image`
  (SeatGeek) automatically - already an absolute URL.
- An artist nobody has claimed never appears here (this searches *from the
  claim table*, not the full artist catalog - use the regular
  `/api/v1/catalog/artists/` search for "every artist").
- `claimed_by[].status` is per-claim (`pending`/`approved`/`rejected`) - one
  artist can have a mix of claimants in different states.
